"""
MCP Server OpenAI notifications模块
定义了服务器使用的通知相关的工具函数
"""

import logging
from typing import Any
from pydantic import ValidationError
from mcp.types import (
    Notification,
    ServerNotification,
    ProgressNotification, 
    ProgressNotificationParams
)
from anyio import BrokenResourceError, ClosedResourceError

logger = logging.getLogger(__name__)

def create_progress_notification(
    request_id: str, 
    progress: float = 1.0,
    message: str | None = None
) -> ProgressNotification:
    """
    创建一个标准的进度通知
    
    Args:
        request_id: 请求ID
        progress: 进度值 (0-1)
        message: 可选的消息
        
    Returns:
        ProgressNotification: 进度通知对象
    """
    return ProgressNotification(
        method="notifications/progress",
        params=ProgressNotificationParams(
            progressToken=request_id,
            progress=min(max(progress, 0.0), 1.0),  # 确保在0-1之间
            message=message or ""
        )
    )

async def safe_send_notification(
    session: Any,
    notification: Notification | ServerNotification,
) -> bool:
    """
    安全地发送通知，捕获并记录任何错误
    
    Args:
        session: 当前会话
        notification: 要发送的通知
        
    Returns:
        bool: 通知是否成功发送
    """
    try:
        # 检查session是否有效
        if not session or not hasattr(session, 'send_notification'):
            logger.warning("Invalid session for sending notification")
            return False

        # 发送通知
        await session.send_notification(notification)
        return True

    except ValidationError as e:
        logger.debug(f"Notification validation error: {e}")
        return False
    except (BrokenResourceError, ClosedResourceError):
        logger.debug("Session closed while sending notification")
        return False
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")
        return False