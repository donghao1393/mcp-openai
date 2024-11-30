"""
MCP Server OpenAI 主服务器模块
实现OpenAI功能的MCP服务器
"""

import asyncio
import logging
import sys
from typing import List, Optional

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from anyio import BrokenResourceError, ClosedResourceError, create_task_group, move_on_after
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
    
    async def _received_notification(self, notification):
        """处理收到的通知"""
        try:
            # 尝试将通知作为取消通知处理
            if getattr(notification, "method", None) == "cancelled":
                try:
                    params = getattr(notification, "params", {})
                    if not isinstance(params, dict):
                        params = {}
                        
                    request_id = str(params.get("requestId", "unknown"))
                    reason = str(params.get("reason", "Operation cancelled"))
                    
                    # 使用带超时的context发送通知
                    with move_on_after(5.0) as scope:  # 5秒超时
                        progress_notification = types.ProgressNotification(
                            method="notifications/progress",
                            params=types.ProgressNotificationParams(
                                progressToken=request_id,
                                progress=1.0,
                                message=reason
                            )
                        )
                        await self._session.send_notification(progress_notification)
                        
                        # 如果超时，记录一个debug日志
                        if scope.cancel_called:
                            logger.debug(f"Notification send timed out for request {request_id}")
                        return
                except Exception as e:
                    logger.warning(f"Error handling cancelled notification: {e}", exc_info=True)
                    try:
                        # 发送一个基本的进度通知作为后备
                        with move_on_after(2.0):  # 2秒超时
                            await self._session.send_notification(types.ProgressNotification(
                                method="notifications/progress",
                                params=types.ProgressNotificationParams(
                                    progressToken="error",
                                    progress=1.0,
                                    message="Operation completed with errors"
                                )
                            ))
                    except Exception as e2:
                        logger.error(f"Failed to send fallback notification: {e2}")
                    return
                    
            # 如果不是取消通知，按常规方式处理
            await super()._received_notification(notification)
        except Exception as e:
            logger.warning(f"Error handling notification: {e}")

def serve(openai_api_key: str) -> OpenAIServer:
    """
    创建并配置OpenAI服务器实例
    
    Args:
        openai_api_key: OpenAI API密钥
        
    Returns:
        OpenAIServer: 配置好的服务器实例
    """
    server = OpenAIServer("openai-server")
    connector = LLMConnector(openai_api_key)

    async def cleanup_session():
        """清理会话资源"""
        try:
            if hasattr(server, 'request_context') and server.request_context:
                with move_on_after(3.0):  # 3秒超时
                    await safe_send_notification(
                        server.request_context.session,
                        types.ProgressNotification(
                            method="notifications/progress",
                            params=types.ProgressNotificationParams(
                                progressToken="cleanup",
                                progress=1.0,
                                message="Cleaning up session"
                            )
                        ),
                        convert_cancelled=False
                    )
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")

    # 存储清理函数
    server.cleanup = cleanup_session

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """返回支持的工具列表"""
        return get_tool_definitions()

    @server.call_tool()
    async def handle_tool_call(name: str, arguments: dict | None) -> List[types.TextContent | types.ImageContent]:
        """
        处理工具调用请求
        
        Args:
            name: 工具名称
            arguments: 工具参数
            
        Returns:
            List[types.TextContent | types.ImageContent]: 工具执行结果
        """
        try:
            if not arguments:
                raise ValueError("未提供参数")

            if name == "ask-openai":
                with move_on_after(90.0) as scope:  # 90秒超时
                    result = await handle_ask_openai(connector, arguments)
                    if scope.cancel_called:
                        logger.warning("Ask OpenAI request timed out")
                        return [types.TextContent(type="text", text="Request timed out after 90 seconds")]
                    return result
            elif name == "create-image":
                with move_on_after(120.0) as scope:  # 120秒超时
                    result = await handle_create_image(server, connector, arguments)
                    if scope.cancel_called:
                        logger.warning("Create image request timed out")
                        return [types.TextContent(type="text", text="Image generation timed out after 120 seconds")]
                    return result

            raise ValueError(f"未知的工具: {name}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool call failed: {error_msg}", exc_info=True)
            return [types.TextContent(type="text", text=f"错误: {error_msg}")]

    return server

@click.command()
@click.option("--openai-api-key", envvar="OPENAI_API_KEY", required=True)
def main(openai_api_key: str):
    """MCP OpenAI服务器入口函数"""
    try:
        async def _run():
            try:
                async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                    server = serve(openai_api_key)
                    try:
                        # 设置服务器的最大消息大小为32MB
                        experimental_capabilities = {
                            "messageSize": {
                                "maxMessageBytes": 32 * 1024 * 1024
                            }
                        }
                        
                        # 启动服务器
                        with move_on_after(180) as scope:  # 全局3分钟超时
                            await server.run(
                                read_stream, write_stream,
                                InitializationOptions(
                                    server_name="openai-server",
                                    server_version="0.3.2",
                                    capabilities=server.get_capabilities(
                                        notification_options=NotificationOptions(tools_changed=True),
                                        experimental_capabilities=experimental_capabilities
                                    )
                                )
                            )
                            if scope.cancel_called:
                                logger.warning("Server run timed out after 180 seconds")
                            else:
                                logger.info("Server session ended normally")
                        
                    except (asyncio.CancelledError, BrokenResourceError, ClosedResourceError) as e:
                        # 正常的会话关闭情况
                        logger.debug(f"Session closed: {str(e)}")
                        
                    except Exception as e:
                        # 检查是否是取消通知引起的异常
                        if "cancelled" in str(e).lower():
                            logger.debug(f"Session cancelled: {str(e)}")
                        else:
                            logger.error(f"Unexpected error during server run: {e}", exc_info=True)
                            raise
                            
                    finally:
                        # 确保在会话结束时进行清理
                        if hasattr(server, 'cleanup'):
                            try:
                                with move_on_after(5.0):  # 清理超时5秒
                                    await server.cleanup()
                            except Exception as e:
                                logger.debug(f"Error during cleanup: {e}")
                    
            except (BrokenResourceError, ClosedResourceError) as e:
                logger.debug(f"Stream connection closed: {str(e)}")
            except Exception as e:
                logger.error(f"Error in server setup: {e}", exc_info=True)
                raise

        asyncio.run(_run())
        
    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
        sys.exit(0)
    except Exception as e:
        if isinstance(e, ExceptionGroup):
            # 处理异常组
            for exc in e.exceptions:
                if "cancelled" in str(exc).lower():
                    logger.debug(f"Session cancelled: {exc}")
                else:
                    logger.error(f"错误: {exc}", exc_info=True)
        else:
            logger.error("服务器运行失败", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()