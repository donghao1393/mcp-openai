"""
MCP Server OpenAI 主服务器模块
实现OpenAI功能的MCP服务器
"""

import asyncio
import logging
import sys
from typing import Any, Dict, Optional, Union
import traceback

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.session import BaseSession, RequestResponder
from anyio import BrokenResourceError, ClosedResourceError
from pydantic import BaseModel, RootModel, ValidationError

from .llm import LLMConnector
from .tools import get_tool_definitions, handle_ask_openai, handle_create_image

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('openai_server.log')  # 添加文件日志
    ]
)
logger = logging.getLogger(__name__)

# 扩展MCP通知定义以支持取消通知
class CancelledNotificationParams(BaseModel):
    """取消通知的参数"""
    requestId: int
    reason: Optional[str] = None

class CancelledNotification(BaseModel):
    """取消通知"""
    method: str = "notifications/cancelled"
    params: CancelledNotificationParams

# 扩展ClientNotification以支持取消通知
class ExtendedClientNotification(RootModel):
    """扩展的客户端通知类型"""
    root: Union[types.ProgressNotification, types.InitializedNotification, 
               types.RootsListChangedNotification, CancelledNotification]

class OpenAIServerSession(BaseSession):
    """扩展的MCP会话，支持取消通知"""
    
    def __init__(self, *args, **kwargs):
        # 将通知类型替换为扩展版本
        kwargs['receive_notification_type'] = ExtendedClientNotification
        super().__init__(*args, **kwargs)

    async def handle_error(self, error: Exception) -> None:
        """增强的错误处理"""
        logger.error(f"Session error occurred: {str(error)}")
        logger.debug(f"Error details: {traceback.format_exc()}")
        await super().handle_error(error)

class OpenAIServer(Server):
    """MCP OpenAI服务器实现"""

    def create_session(self, read_stream, write_stream):
        """创建支持扩展通知的会话"""
        return OpenAIServerSession(
            read_stream=read_stream,
            write_stream=write_stream,
            receive_request_type=types.ClientRequest,
            receive_notification_type=ExtendedClientNotification,
        )

    async def _handle_incoming_message(self, message: Any) -> None:
        """处理传入消息的逻辑，增强错误处理"""
        try:
            # 1. 处理请求响应者
            if isinstance(message, RequestResponder):
                await super()._handle_incoming_message(message)
                return

            # 2. 处理客户端通知
            if isinstance(message, ExtendedClientNotification):
                await self._handle_notification(message)
                return

            # 3. 处理其他消息类型
            if isinstance(message, Exception):
                logger.error(f"Received error: {message}", exc_info=True)
                return

            logger.warning(f"Received unsupported message type: {type(message)}")

        except (BrokenResourceError, ClosedResourceError) as e:
            logger.debug(f"Connection closed during message handling: {e}")
            # 尝试优雅关闭
            await self.shutdown()
        except ValidationError as e:
            logger.error(f"Validation error during message handling: {e.errors()}")
        except asyncio.CancelledError:
            logger.info("Server operation cancelled")
            raise  # 重新抛出取消异常以允许正常的异步取消
        except Exception as e:
            logger.critical(f"Unexpected error during message handling: {e}", exc_info=True)
            # 继续运行，不中断服务

    async def _handle_notification(self, notification: ExtendedClientNotification) -> None:
        """处理通知的逻辑，增强错误处理"""
        try:
            match notification.root:
                case CancelledNotification():
                    params = notification.root.params
                    logger.info(
                        f"Request {params.requestId} cancelled"
                        f"{f': {params.reason}' if params.reason else ''}"
                    )
                case types.ProgressNotification():
                    params = notification.root.params
                    if hasattr(params, 'progressToken') and hasattr(params, 'progress'):
                        logger.debug(
                            f"Progress notification: token={params.progressToken}, "
                            f"progress={params.progress}"
                        )
                case types.InitializedNotification():
                    logger.debug("Server initialized notification")
                case types.RootsListChangedNotification():
                    logger.debug("Roots list changed notification")
                case _:
                    logger.warning(f"Unknown notification: {notification.root}")

        except ValidationError as e:
            logger.error(f"Notification validation error: {e.errors()}")
        except Exception as e:
            logger.error(f"Error handling notification: {e}", exc_info=True)

    async def shutdown(self) -> None:
        """优雅关闭服务器"""
        logger.info("Initiating server shutdown...")
        try:
            # 实现优雅关闭逻辑
            # 例如关闭所有活跃连接，清理资源等
            await super().shutdown()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
        finally:
            logger.info("Server shutdown completed")

def serve(openai_api_key: str) -> OpenAIServer:
    """创建并配置服务器实例"""
    server = OpenAIServer("openai-server")
    connector = LLMConnector(openai_api_key)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """返回支持的工具列表"""
        try:
            return get_tool_definitions()
        except Exception as e:
            logger.error(f"Error listing tools: {e}", exc_info=True)
            raise

    @server.call_tool()
    async def handle_tool_call(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent]:
        """处理工具调用"""
        if not arguments:
            raise ValueError("未提供参数")

        try:
            match name:
                case "ask-openai":
                    return await handle_ask_openai(connector, arguments)
                case "create-image":
                    return await handle_create_image(server, connector, arguments)
                case _:
                    raise ValueError(f"未知的工具: {name}")
        except asyncio.CancelledError:
            logger.info("操作被取消")
            return [types.TextContent(type="text", text="操作已取消")]
        except TimeoutError as e:
            logger.warning(f"操作超时: {e}")
            return [types.TextContent(type="text", text=f"操作超时: {e}")]
        except Exception as e:
            logger.error(f"操作失败: {e}", exc_info=True)
            return [types.TextContent(type="text", text=f"操作失败: {e}")]

    return server

async def run_server(server: OpenAIServer) -> None:
    """运行服务器的核心逻辑"""
    try:
        # 设置实验性功能，声明支持取消通知
        experimental_capabilities = {
            "messageSize": {
                "maxMessageBytes": 32 * 1024 * 1024  # 32MB
            },
            "notifications": {
                "cancelled": True  # 声明支持取消通知
            }
        }

        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            # 启动服务器
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="openai-server",
                    server_version="0.3.2",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(tools_changed=True),
                        experimental_capabilities=experimental_capabilities
                    )
                )
            )

    except (BrokenResourceError, ClosedResourceError) as e:
        logger.info(f"Connection closed: {e}")
    except ValidationError as e:
        logger.error(f"Validation error: {e.errors()}")
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        if isinstance(e, ExceptionGroup):
            for exc in e.exceptions:
                if isinstance(exc, ValidationError):
                    logger.error(f"Validation error in group: {exc.errors()}")
                elif isinstance(exc, (BrokenResourceError, ClosedResourceError)):
                    logger.debug(f"Connection closed in group: {exc}")
                else:
                    logger.error(f"Error in group: {exc}", exc_info=True)
        else:
            logger.error(f"Server error: {e}", exc_info=True)
    finally:
        # 确保服务器正确关闭
        await server.shutdown()

async def _run():
    """服务器启动的核心异步函数"""
    try:
        server = serve(sys.argv[1] if len(sys.argv) > 1 else None)
        await run_server(server)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 确保所有资源都被清理
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

@click.command()
@click.option("--openai-api-key", envvar="OPENAI_API_KEY", required=True)
def main(openai_api_key: str):
    """MCP OpenAI服务器入口函数"""
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
        sys.exit(0)
    except Exception as e:
        logger.error("服务器运行失败", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()