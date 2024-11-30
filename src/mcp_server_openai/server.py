"""
MCP Server OpenAI 主服务器模块
实现OpenAI功能的MCP服务器
"""

import asyncio
import logging
import sys
from typing import Any, Dict

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.session import RequestResponder
from anyio import BrokenResourceError, ClosedResourceError
from pydantic import ValidationError

from .llm import LLMConnector
from .tools import get_tool_definitions, handle_ask_openai, handle_create_image

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class OpenAIServer(Server):
    """MCP OpenAI服务器实现"""

    async def _handle_incoming_message(self, message: Any) -> None:
        """处理传入消息的改进逻辑"""
        try:
            # 1. 处理取消通知
            if isinstance(message, dict) and message.get("method") == "cancelled":
                logger.debug("Received cancelled notification")
                params = message.get("params", {})
                request_id = params.get("requestId", "unknown")
                reason = params.get("reason", "unknown")
                logger.info(f"Request {request_id} cancelled: {reason}")
                return

            # 2. 处理请求响应者
            if isinstance(message, RequestResponder):
                await super()._handle_incoming_message(message)
                return

            # 3. 处理客户端通知
            if isinstance(message, types.ClientNotification):
                await self._received_notification(message)
                return

            # 4. 处理其他消息
            logger.warning(f"Received unknown message type: {type(message)}")

        except (BrokenResourceError, ClosedResourceError) as e:
            logger.debug(f"Connection closed during message handling: {e}")
            raise  # 重新抛出以便上层处理
        except ValidationError as e:
            logger.debug(f"Validation error during message handling: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during message handling: {e}", exc_info=True)

    async def _received_notification(self, notification: types.ClientNotification) -> None:
        """处理收到的通知的改进逻辑"""
        try:
            match notification.method:
                case "notifications/progress":
                    logger.debug(f"Progress notification: {notification.params}")
                case "notifications/initialized":
                    logger.debug("Server initialized notification")
                case "notifications/roots/list_changed":
                    logger.debug("Roots list changed notification")
                case _:
                    logger.warning(f"Unknown notification method: {notification.method}")
        except Exception as e:
            logger.error(f"Error handling notification: {e}", exc_info=True)

def serve(openai_api_key: str) -> OpenAIServer:
    """创建并配置服务器实例"""
    server = OpenAIServer("openai-server")
    connector = LLMConnector(openai_api_key)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """返回支持的工具列表"""
        return get_tool_definitions()

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
                ),
                raise_exceptions=True  # 启用异常抛出以便更好地调试
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
                elif isinstance(exc, (BrokenResourceError, ClosedResourceError)):
                    logger.debug(f"Connection closed in group: {exc}")
                else:
                    logger.error(f"Error in group: {exc}", exc_info=True)
        else:
            logger.error(f"Server error: {e}", exc_info=True)

async def _run():
    """服务器启动的核心异步函数"""
    try:
        server = serve(sys.argv[1] if len(sys.argv) > 1 else None)
        await run_server(server)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise  # 重新抛出异常以确保正确的退出状态

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