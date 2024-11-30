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

        # 注册工具处理方法
        self.request_handlers[types.CallToolRequest] = self._handle_tool_request
        
    async def _handle_ask_openai(self, arguments: Dict[str, Any]) -> List[Union[types.TextContent, types.ImageContent]]:
        """处理OpenAI问答请求"""
        return await handle_ask_openai(self.connector, arguments)
        
    async def _handle_create_image(self, arguments: Dict[str, Any]) -> List[Union[types.TextContent, types.ImageContent]]:
        """处理图像生成请求"""
        return await handle_create_image(self, self.connector, arguments)

    async def _handle_tool_request(self, req: types.CallToolRequest) -> types.ServerResult:
        """内部工具请求处理器"""
        try:
            if req.params.name not in self.handlers:
                raise ValueError(f"未知的工具: {req.params.name}")
                
            handler = self.handlers[req.params.name]
            if req.params.name == "create-image":
                results = await handler(self, self.connector, req.params.arguments or {})
            else:
                results = await handler(self.connector, req.params.arguments or {})
                
            return types.ServerResult(
                types.CallToolResult(content=list(results), isError=False)
            )
            
        except Exception as e:
            logger.error(f"工具调用错误: {e}", exc_info=True)
            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text=str(e))],
                    isError=True
                )
            )

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
        # 移除对super().shutdown()的调用，因为父类没有这个方法