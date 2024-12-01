"""
MCP Server OpenAI notifications模块
定义了服务器使用的通知相关的工具函数
"""

import logging
from typing import Any, Optional
import anyio
from pydantic import ValidationError
from mcp.types import (
    ServerNotification,
    ProgressNotification, 
    ProgressNotificationParams
)
from anyio import BrokenResourceError, ClosedResourceError

logger = logging.getLogger(__name__)

async def create_progress_notification(
    progress_token: str | int,
    progress: float,
    total: Optional[float] = None
) -> ServerNotification:
    """
    创建标准的进度通知
    
    Args:
        progress_token: 进度令牌
        progress: 当前进度
        total: 总进度（可选）
        
    Returns:
        ServerNotification: 包装好的进度通知
    """
    params = ProgressNotificationParams(
        progressToken=progress_token,
        progress=progress,
        total=total if total is not None else 100
    )
    notification = ProgressNotification(
        method="notifications/progress",
        params=params
    )
    return ServerNotification(root=notification)

async def safe_send_notification(
    session: Any,
    notification: ServerNotification,
) -> bool:
    """
    安全地发送标准MCP通知，捕获并记录任何错误
    
    Args:
        session: 当前会话
        notification: 要发送的通知
        
    Returns:
        bool: 通知是否成功发送
    """
    if not session or not hasattr(session, 'send_notification'):
        logger.warning("Invalid session for sending notification")
        return False
        
    try:
        # 使用CancelScope防止在关闭过程中被取消
        async with anyio.CancelScope(shield=True):
            # 在发送前验证通知格式
            if isinstance(notification.root, ProgressNotification):
                try:
                    params = notification.root.params
                    if not isinstance(params.progressToken, (str, int)):
                        logger.error(f"Invalid progress token type: {type(params.progressToken)}")
                        return False
                    if not isinstance(params.progress, (int, float)):
                        logger.error(f"Invalid progress value type: {type(params.progress)}")
                        return False
                    if params.total is not None and not isinstance(params.total, (int, float)):
                        logger.error(f"Invalid total value type: {type(params.total)}")
                        return False
                except Exception as e:
                    logger.error(f"Invalid progress notification format: {e}")
                    return False

            await session.send_notification(notification)
            return True

    except ValidationError as e:
        logger.warning(f"Notification validation error: {e.errors()}")
        return False
    except (BrokenResourceError, ClosedResourceError):
        # 这些错误通常发生在服务器关闭时，不需要打印堆栈
        logger.debug("Session closed while sending notification")
        return False
    except Exception as e:
        logger.error(f"Failed to send notification: {e}", exc_info=True)
        return False