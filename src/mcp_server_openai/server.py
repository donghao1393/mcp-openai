"""
MCP Server OpenAI 主服务器模块
实现OpenAI功能的MCP服务器
"""

import asyncio
import logging
import sys
from typing import Any, Dict, Optional, Union
import traceback
import signal
import anyio
from anyio import BrokenResourceError, ClosedResourceError
import contextlib

import mcp.server
import mcp.server.stdio
from mcp.server.models import InitializationOptions
from .openai import OpenAIServer

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

async def run_server(server: OpenAIServer) -> None:
    """运行服务器的核心逻辑"""
    # 创建关闭事件
    shutdown_event = asyncio.Event()
    shutdown_complete = asyncio.Event()
    watchdog_task = None
    
    def signal_handler(signum, frame):
        """同步信号处理函数"""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name}")
        # 使用 call_soon_threadsafe 确保在正确的线程中设置事件
        asyncio.get_event_loop().call_soon_threadsafe(shutdown_event.set)
    
    async def watchdog():
        """监控 stdin 是否关闭的看门狗"""
        try:
            while not shutdown_event.is_set():
                try:
                    if sys.stdin.closed:
                        logger.warning("stdin was closed, initiating shutdown")
                        shutdown_event.set()
                        break
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Watchdog check error: {e}", exc_info=True)
                    await asyncio.sleep(1)  # 避免快速循环
        except asyncio.CancelledError:
            logger.debug("Watchdog task cancelled")
        except Exception as e:
            logger.error(f"Watchdog error: {e}", exc_info=True)
        finally:
            # 确保设置关闭事件
            shutdown_event.set()

    async def cleanup_tasks(*tasks):
        """清理任务的辅助函数"""
        for task in tasks:
            if task and not task.done():
                try:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                except Exception as e:
                    logger.error(f"Error cleaning up task: {e}", exc_info=True)

    async def safe_shutdown(server_instance, server_task=None):
        """安全关闭服务器"""
        try:
            if server_task and not server_task.done():
                await cleanup_tasks(server_task)
            await server_instance.shutdown()
        except Exception as e:
            logger.error(f"Error during safe shutdown: {e}", exc_info=True)
        finally:
            shutdown_complete.set()

    try:
        # 设置信号处理
        original_handlers = {}
        signals_to_handle = [signal.SIGINT, signal.SIGTERM]
        if sys.platform != "win32":
            signals_to_handle.append(signal.SIGUSR1)
            
        for sig in signals_to_handle:
            original_handlers[sig] = signal.signal(sig, signal_handler)

        # 设置通知选项
        notification_options = mcp.server.NotificationOptions(
            prompts_changed=False,
            resources_changed=False,
            tools_changed=True
        )

        # 设置实验性功能
        experimental_capabilities = {
            "messageSize": {
                "maxMessageBytes": 32 * 1024 * 1024  # 32MB
            },
            "notifications": {
                "cancelled": True
            }
        }

        try:
            # 启动看门狗
            watchdog_task = asyncio.create_task(watchdog())

            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                # 启动服务器
                capabilities = server.get_capabilities(
                    notification_options=notification_options,
                    experimental_capabilities=experimental_capabilities
                )
                
                # 创建服务器运行任务
                server_task = asyncio.create_task(
                    server.run(
                        read_stream,
                        write_stream,
                        InitializationOptions(
                            server_name=server.name,
                            server_version="0.3.2",
                            capabilities=capabilities
                        )
                    )
                )
                
                # 创建关闭事件等待任务
                shutdown_task = asyncio.create_task(shutdown_event.wait())
                
                try:
                    # 等待任务完成或收到关闭信号
                    done, pending = await asyncio.wait(
                        [server_task, shutdown_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    if shutdown_event.is_set():
                        logger.info("Initiating graceful shutdown...")
                        await safe_shutdown(server, server_task)
                    else:
                        # 检查服务器任务是否有异常
                        if server_task in done and server_task.exception():
                            logger.error("Server task failed", exc_info=server_task.exception())
                        await safe_shutdown(server, server_task)

                    # 取消并等待所有pending的任务完成
                    if pending:
                        await cleanup_tasks(*pending)
                            
                except asyncio.CancelledError:
                    logger.info("Server task was cancelled")
                    await safe_shutdown(server, server_task)
                    raise
                except Exception as e:
                    logger.error(f"Error in server task: {e}", exc_info=True)
                    await safe_shutdown(server, server_task)
                    raise

        except (BrokenResourceError, ClosedResourceError) as e:
            logger.info(f"Connection closed: {e}")
            await safe_shutdown(server)
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            await safe_shutdown(server)
            raise

    except Exception as e:
        if not isinstance(e, (KeyboardInterrupt, SystemExit)):
            logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        # 清理所有剩余任务
        await cleanup_tasks(watchdog_task)
        
        # 恢复原始信号处理器
        for sig, handler in original_handlers.items():
            try:
                signal.signal(sig, handler)
            except Exception as e:
                logger.error(f"Error restoring signal handler for {sig}: {e}")

        # 确保完成所有清理工作
        if not shutdown_complete.is_set():
            try:
                await server.shutdown()
            except Exception as e:
                logger.error(f"Error during final shutdown: {e}", exc_info=True)

def main():
    """程序入口点"""
    try:
        server = OpenAIServer()
        anyio.run(run_server, server)
    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()