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
    total: Optional[float] = None,
    *,
    is_final: bool = False
) -> ServerNotification:
    """
    创建标准的进度通知
    
    Args:
        progress_token: 进度令牌
        progress: 当前进度
        total: 总进度（可选）
        is_final: 是否为最终通知
        
    Returns:
        ServerNotification: 包装好的进度通知
    """
    # 确保 progress 在有效范围内
    progress = max(0.0, min(float(progress), float(total if total is not None else 100)))
    
    params = ProgressNotificationParams(
        progressToken=progress_token,
        progress=progress,
        total=total if total is not None else 100
    )
    notification = ProgressNotification(
        method="notifications/progress",
        params=params
    )
    logger.debug(f"Created progress notification: {notification}")
    return ServerNotification(root=notification)

class NotificationManager:
    """通知管理器，处理通知的生命周期和错误处理"""
    
    def __init__(self, session: Any):
        self.session = session
        self._closed = False
        self._debug_id = id(self)  # 添加一个调试ID
        logger.debug(f"Creating NotificationManager {self._debug_id}")
        
    @property
    def is_closed(self) -> bool:
        return self._closed
        
    async def close(self):
        """标记通知管理器为已关闭"""
        logger.debug(f"Closing NotificationManager {self._debug_id}")
        self._closed = True
        
    async def send_notification(
        self,
        notification: ServerNotification,
        *,
        shield: bool = True
    ) -> bool:
        """
        安全地发送标准MCP通知，捕获并记录任何错误
        
        Args:
            notification: 要发送的通知
            shield: 是否保护通知免受取消影响
            
        Returns:
            bool: 通知是否成功发送
        """
        if self.is_closed:
            logger.debug(f"NotificationManager {self._debug_id} is closed, skipping notification: {notification}")
            return False
            
        if not self.session or not hasattr(self.session, 'send_notification'):
            logger.warning(f"NotificationManager {self._debug_id} has invalid session for notification: {notification}")
            return False
        
        async def _send() -> bool:
            try:
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

                        logger.debug(f"NotificationManager {self._debug_id} sending progress notification: progress={params.progress}, total={params.total}")
                            
                    except Exception as e:
                        logger.error(f"Invalid progress notification format: {e}")
                        return False

                await self.session.send_notification(notification)
                logger.debug(f"NotificationManager {self._debug_id} successfully sent notification")
                return True

            except ValidationError as e:
                logger.warning(f"NotificationManager {self._debug_id} notification validation error: {e.errors()}")
                return False
            except (BrokenResourceError, ClosedResourceError):
                logger.debug(f"NotificationManager {self._debug_id} session closed while sending notification")
                return False
            except Exception as e:
                logger.error(f"NotificationManager {self._debug_id} failed to send notification: {e}", exc_info=True)
                return False
                
        if shield:
            try:
                logger.debug(f"NotificationManager {self._debug_id} sending notification with shield")
                async with anyio.CancelScope(shield=True):
                    return await _send()
            except Exception as e:
                logger.error(f"NotificationManager {self._debug_id} error in shielded notification send: {e}")
                return False
        else:
            logger.debug(f"NotificationManager {self._debug_id} sending notification without shield")
            return await _send()
            
    async def __aenter__(self):
        """异步上下文管理器入口"""
        logger.debug(f"Entering NotificationManager {self._debug_id} context")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，确保清理"""
        logger.debug(f"Exiting NotificationManager {self._debug_id} context: exc_type={exc_type}")
        await self.close()