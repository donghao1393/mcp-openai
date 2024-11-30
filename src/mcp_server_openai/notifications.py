"""
MCP Server OpenAI notifications模块
定义了服务器使用的各种通知类型和通知相关的工具函数
"""

import logging
from typing import Literal
from pydantic import BaseModel
from mcp.types import Notification, NotificationParams, ProgressNotification, ProgressNotificationParams
from anyio import BrokenResourceError, ClosedResourceError

logger = logging.getLogger(__name__)

class CancelledParams(NotificationParams):
    """取消通知的参数"""
    requestId: int
    reason: str | None = None

class CancelledNotification(Notification[CancelledParams, Literal["cancelled"]]):
    """请求取消的通知"""
    method: Literal["cancelled"] = "cancelled"
    params: CancelledParams

async def safe_send_notification(session, notification, convert_cancelled=True):
    """
    安全地发送通知，捕获并记录任何错误
    
    Args:
        session: 当前会话
        notification: 要发送的通知
        convert_cancelled: 是否将cancelled通知转换为progress通知
    """
    try:
        if convert_cancelled and isinstance(notification, CancelledNotification):
            # 转换为progress通知
            notification = ProgressNotification(
                method="notifications/progress",
                params=ProgressNotificationParams(
                    progressToken=str(notification.params.requestId),
                    progress=1.0,
                    message=notification.params.reason or "Operation cancelled"
                )
            )
        
        await session.send_notification(notification)
    except (BrokenResourceError, ClosedResourceError):
        logger.debug("Session closed while sending notification")
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")