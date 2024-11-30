"""OpenAI服务器实现"""

import logging
import os
from typing import Any, Dict, List, Optional, Union, Sequence

import mcp.server as server
import mcp.types as types
from .llm import LLMConnector
from .tools import get_tool_definitions, handle_ask_openai, handle_create_image
from .types import CancelledNotification, CancelledNotificationParams

logger = logging.getLogger(__name__)

class OpenAIServer(server.Server):
    """OpenAI服务器类"""
    
    def __init__(self):
        """初始化OpenAI服务器"""
        super().__init__(name="mcp-openai")  # 添加name参数
        
        # 获取API密钥
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未设置OPENAI_API_KEY环境变量")
            
        # 初始化连接器
        self.connector = LLMConnector(self.api_key)
        
        # 注册处理方法
        self.handlers = {
            "ask-openai": self._handle_ask_openai,
            "create-image": self._handle_create_image
        }
        
        # 设置工具定义
        self._tools = get_tool_definitions()
        
    @server.Server.call_tool()
    async def handle_call_tool(
        self,
        name: str,
        arguments: Dict[str, Any]
    ) -> Sequence[Union[types.TextContent, types.ImageContent, types.EmbeddedResource]]:
        """处理工具调用"""
        if name not in self.handlers:
            raise ValueError(f"未知的工具: {name}")
            
        handler = self.handlers[name]
        if name == "create-image":
            return await handler(self, self.connector, arguments)
        return await handler(self.connector, arguments)

    @server.Server.list_tools()
    async def handle_list_tools(self) -> List[types.Tool]:
        """返回支持的工具列表"""
        return self._tools

    async def shutdown(self) -> None:
        """关闭服务器"""
        logger.info("关闭OpenAI服务器...")
        if self.connector and hasattr(self.connector, 'close'):
            try:
                await self.connector.close()
            except Exception as e:
                logger.error(f"Error closing connector: {e}")
        await super().shutdown()