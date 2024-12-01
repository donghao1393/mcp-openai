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
from anyio import BrokenResourceError, ClosedResourceError, WouldBlock
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

class StreamManager:
    """流管理器，用于处理读写流的生命周期"""
    def __init__(self, read_stream, write_stream):
        self.read_stream = read_stream
        self.write_stream = write_stream
        self._closed = False

    async def close(self):
        """安全关闭流"""
        if not self._closed:
            try:
                # 确保写入缓冲区被刷新
                if hasattr(self.write_stream, 'flush'):
                    try:
                        async with asyncio.timeout(5):  # 5秒超时
                            await self.write_stream.flush()
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning(f"Error flushing write stream: {e}")
            except Exception as e:
                logger.error(f"Error during stream cleanup: {e}")
            finally:
                self._closed = True

    @contextlib.asynccontextmanager
    async def would_block_handler(self, retries=3, delay=0.1):
        """处理 WouldBlock 异常的重试逻辑"""
        for i in range(retries):
            try:
                yield
                break
            except WouldBlock:
                if i < retries - 1:
                    await asyncio.sleep(delay * (i + 1))  # 指数退避
                    continue
                raise

async def run_server(server: OpenAIServer) -> None:
    """运行服务器的核心逻辑"""
    # 创建关闭事件
    shutdown_event = asyncio.Event()
    shutdown_complete = asyncio.Event()
    watchdog_task = None
    stream_manager = None
    
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
                    try:
                        # 使用更长的超时时间来等待任务清理
                        async with asyncio.timeout(5):  # 5秒超时
                            await task
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        logger.warning(f"Task cleanup timed out or was cancelled for task: {task}")
                except Exception as e:
                    logger.error(f"Error cleaning up task: {e}", exc_info=True)

    async def handle_connection(server_instance, stream_mgr):
        """处理单个连接的逻辑"""
        try:
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

            # 启动服务器
            capabilities = server_instance.get_capabilities(
                notification_options=notification_options,
                experimental_capabilities=experimental_capabilities
            )

            # 使用改进后的 would_block_handler
            async with stream_mgr.would_block_handler():
                await server_instance.run(
                    stream_mgr.read_stream,
                    stream_mgr.write_stream,
                    InitializationOptions(
                        server_name=server_instance.name,
                        server_version="0.3.2",
                        capabilities=capabilities
                    )
                )
        except asyncio.CancelledError:
            logger.info("Connection handler was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in connection handler: {e}", exc_info=True)
            raise

    async def safe_shutdown(server_instance, server_task=None):
        """安全关闭服务器"""
        try:
            if server_task and not server_task.done():
                await cleanup_tasks(server_task)
            
            # 如果有流管理器，确保它被正确关闭
            if stream_manager:
                await stream_manager.close()
            
            try:
                # 设置关闭超时
                async with asyncio.timeout(10):  # 10秒超时
                    await server_instance.shutdown()
            except asyncio.TimeoutError:
                logger.error("Server shutdown timed out")
            except Exception as e:
                logger.error(f"Error during server shutdown: {e}", exc_info=True)
                
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

        try:
            # 启动看门狗
            watchdog_task = asyncio.create_task(watchdog())

            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                # 创建流管理器
                stream_manager = StreamManager(read_stream, write_stream)
                
                # 创建连接处理任务
                server_task = asyncio.create_task(
                    handle_connection(server, stream_manager)
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
                    elif server_task in done:
                        if server_task.exception():
                            logger.error("Server task failed", exc_info=server_task.exception())
                    
                    # 执行安全关闭
                    await safe_shutdown(server, server_task)

                    # 取消并等待所有pending的任务完成
                    for task in pending:
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception) as e:
                                logger.debug(f"Task cancelled during shutdown: {e}")
                            
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