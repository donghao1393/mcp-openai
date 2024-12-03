"""OpenAI服务器实现"""

import logging
import os
import asyncio
from typing import Any, Dict, List, Optional, Union, Sequence
from anyio import move_on_after

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
        super().__init__(name="mcp-openai")
        
        # 获取API密钥
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未设置OPENAI_API_KEY环境变量")
            
        # 初始化连接器
        self.connector = LLMConnector(self.api_key)
        self._closing = False
        self._closed = False
        self._close_event = asyncio.Event()
        
        # 注册处理方法
        self.handlers = {
            "ask-openai": self._handle_ask_openai,
            "create-image": self._handle_create_image
        }
        
        # 设置工具定义
        self._tools = get_tool_definitions()
        
        # 注册tool请求处理器
        self.request_handlers[types.CallToolRequest] = self._handle_tool_request
        
        # 注册list_tools处理器
        @self.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return self._tools
    
    async def _handle_ask_openai(self, connector: LLMConnector, arguments: Dict[str, Any]) -> List[Union[types.TextContent, types.ImageContent]]:
        """处理OpenAI问答请求"""
        if self._closed or self._closing:
            raise RuntimeError("Server is closing or closed")
        return await handle_ask_openai(connector, arguments)
        
    async def _handle_create_image(self, connector: LLMConnector, arguments: Dict[str, Any]) -> List[Union[types.TextContent, types.ImageContent]]:
        """处理图像生成请求"""
        if self._closed or self._closing:
            raise RuntimeError("Server is closing or closed")
        return await handle_create_image(self, connector, arguments)

    async def _handle_tool_request(self, req: types.CallToolRequest) -> types.ServerResult:
        """内部工具请求处理器"""
        if self._closed or self._closing:
            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text="服务器正在关闭")],
                    isError=True
                )
            )
        
        try:
            if req.params.name not in self.handlers:
                raise ValueError(f"未知的工具: {req.params.name}")
                
            handler = self.handlers[req.params.name]
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

    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        关闭服务器，清理资源
        
        Args:
            timeout: 关闭操作的超时时间（秒）
            
        Raises:
            TimeoutError: 如果关闭操作超时
            RuntimeError: 如果服务器已在关闭过程中
        """
        if self._closed:
            logger.debug("Server already closed")
            return
            
        if self._closing:
            logger.warning("Server is already closing")
            await self._close_event.wait()
            return
            
        self._closing = True
        logger.info("关闭OpenAI服务器...")
        
        try:
            with move_on_after(timeout) as scope:
                # 关闭LLM连接器
                if hasattr(self, 'connector') and self.connector:
                    try:
                        await self.connector.close(timeout=timeout/2)
                    except Exception as e:
                        logger.error(f"Error closing LLM connector: {e}")
                        raise

                # 清理其他资源
                # Note: 目前没有其他需要清理的资源，但保留此处以便未来扩展
                
                logger.info("OpenAI服务器关闭完成")
                
            if scope.cancel_called:
                logger.error(f"Server shutdown timed out after {timeout} seconds")
                raise TimeoutError("Failed to shutdown server within timeout period")
                
        except Exception as e:
            logger.error(f"服务器关闭过程中发生错误: {e}", exc_info=True)
            raise
        finally:
            self._closed = True
            self._closing = False
            self._close_event.set()