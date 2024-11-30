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

async def safe_send_notification(
    session: Any,
    notification: Notification | ServerNotification,
) -> bool:
    """
    安全地发送标准MCP通知，捕获并记录任何错误
    
    Args:
        session: 当前会话
        notification: 要发送的通知
        
    Returns:
        bool: 通知是否成功发送
    """
    try:
        if not session or not hasattr(session, 'send_notification'):
            logger.warning("Invalid session for sending notification")
            return False

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