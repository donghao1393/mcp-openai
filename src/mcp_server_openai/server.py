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

# ... [其他导入保持不变]

# 配置日志记录（改为文件优先，避免 stdout 关闭影响日志记录）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('openai_server.log'),  # 文件日志放在第一位
        logging.StreamHandler()  # stdout 日志放在第二位
    ]
)
logger = logging.getLogger(__name__)

# ... [中间代码保持不变]

async def run_server(server: OpenAIServer) -> None:
    """运行服务器的核心逻辑"""
    async def handle_signal(sig):
        """处理信号的协程"""
        logger.info(f"Received signal {sig.name}")
        await server.shutdown()
        
    async def watchdog():
        """监控 stdin 是否关闭的看门狗"""
        try:
            while True:
                if sys.stdin.closed:
                    logger.warning("stdin was closed, initiating shutdown")
                    await server.shutdown()
                    break
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Watchdog error: {e}", exc_info=True)

    try:
        # 设置信号处理
        async with anyio.create_task_group() as tg:
            if sys.platform != "win32":  # Windows 不支持 SIGUSR1
                tg.start_soon(lambda: handle_signal(signal.SIGUSR1))
            tg.start_soon(lambda: handle_signal(signal.SIGTERM))
            tg.start_soon(lambda: handle_signal(signal.SIGINT))
            tg.start_soon(watchdog)  # 启动看门狗

            # 设置实验性功能
            experimental_capabilities = {
                "messageSize": {
                    "maxMessageBytes": 32 * 1024 * 1024  # 32MB
                },
                "notifications": {
                    "cancelled": True  # 声明支持取消通知
                }
            }

            try:
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
                # 不要在这里重新抛出异常，让程序继续执行清理流程
            except Exception as e:
                logger.error(f"Server error: {e}", exc_info=True)

    except anyio.ExceptionGroup as e:
        for exc in e.exceptions:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                logger.info("Server stopped by system")
            else:
                logger.error(f"Error in task group: {exc}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        # 确保完成所有清理工作
        try:
            await server.shutdown()
        except Exception as e:
            logger.error(f"Error during final shutdown: {e}", exc_info=True)
        
        # 确保日志被写入
        for handler in logging.getLogger().handlers:
            handler.flush()
            if isinstance(handler, logging.FileHandler):
                handler.close()

# ... [其余代码保持不变]