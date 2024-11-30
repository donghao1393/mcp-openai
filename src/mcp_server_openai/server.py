"""
MCP Server OpenAI 主服务器模块
实现OpenAI功能的MCP服务器
"""

import asyncio
import logging
import sys
from typing import List, Optional, Union, Dict, Any

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from anyio import BrokenResourceError, ClosedResourceError, create_task_group
from pydantic import ValidationError

from .llm import LLMConnector
from .notifications import CancelledNotification, CancelledParams, safe_send_notification
from .tools import get_tool_definitions, handle_ask_openai, handle_create_image

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class OpenAIServer(Server):
    """MCP OpenAI服务器实现"""
    
    async def _received_notification(self, notification: Union[dict, Any]):
        """处理收到的通知"""
        try:
            # 防止空通知
            if not notification:
                logger.debug("Received empty notification")
                return
                
            # 处理取消通知
            if isinstance(notification, dict) and notification.get("method") == "cancelled":
                await self._handle_cancelled_notification(notification)
                return
            
            # 处理其他通知
            try:
                await super()._received_notification(notification)
            except ValidationError as e:
                logger.debug(f"Validation error in standard notification: {e}")
            except Exception as e:
                logger.warning(f"Error in standard notification: {e}")
                
        except BrokenResourceError:
            logger.debug("Connection was closed while handling notification")
        except Exception as e:
            # 记录但不传播异常
            logger.warning(f"Error in notification handling: {e}")

    async def _handle_cancelled_notification(self, notification: dict):
        """专门处理取消通知的方法"""
        try:
            params = notification.get("params", {})
            request_id = str(params.get("requestId", "unknown"))
            reason = str(params.get("reason", "Operation cancelled"))
            
            # 构造进度通知
            progress_notification = types.ProgressNotification(
                method="notifications/progress",
                params=types.ProgressNotificationParams(
                    progressToken=request_id,
                    progress=1.0,  # 表示完成
                    message=reason
                )
            )
            
            # 安全发送通知
            await safe_send_notification(
                self._session,
                types.ServerNotification(progress_notification),
                convert_cancelled=False  # 已经是转换后的通知了
            )
        except ValidationError as e:
            logger.debug(f"Validation error converting cancel to progress: {e}")
        except Exception as e:
            logger.warning(f"Error handling cancelled notification: {e}")

def serve(openai_api_key: str) -> OpenAIServer:
    """创建并配置服务器实例"""
    server = OpenAIServer("openai-server")
    connector = LLMConnector(openai_api_key)

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """返回支持的工具列表"""
        return get_tool_definitions()

    @server.call_tool()
    async def handle_tool_call(name: str, arguments: dict | None) -> List[types.TextContent | types.ImageContent]:
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

async def run_server(server: OpenAIServer, read_stream, write_stream):
    """运行服务器的核心逻辑"""
    try:
        experimental_capabilities = {
            "messageSize": {
                "maxMessageBytes": 32 * 1024 * 1024
            }
        }

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
            ),
            raise_exceptions=False
        )

    except (BrokenResourceError, ClosedResourceError) as e:
        logger.debug(f"Connection closed: {e}")
    except ValidationError as e:
        logger.debug(f"Validation error: {e}")
    except Exception as e:
        if isinstance(e, ExceptionGroup):
            for exc in e.exceptions:
                if isinstance(exc, ValidationError):
                    logger.debug(f"Validation error in group: {exc}")
                elif "cancelled" in str(exc).lower():
                    logger.debug(f"Cancellation in group: {exc}")
                else:
                    logger.error(f"Error in group: {exc}", exc_info=True)
        else:
            logger.error(f"Server error: {e}", exc_info=True)

async def _run():
    """服务器启动的核心异步函数"""
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            server = serve(sys.argv[1] if len(sys.argv) > 1 else None)
            await run_server(server, read_stream, write_stream)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

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