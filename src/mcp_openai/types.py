"""自定义类型定义模块"""
from typing import Optional
from pydantic import BaseModel

class CancelledNotificationParams(BaseModel):
    """取消通知的参数"""
    requestId: int
    reason: Optional[str] = None

class CancelledNotification(BaseModel):
    """取消通知的定义"""
    method: str = "notifications/cancelled"
    params: CancelledNotificationParams
