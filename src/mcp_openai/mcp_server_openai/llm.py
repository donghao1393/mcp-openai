"""
MCP Server OpenAI LLM连接器模块
处理与OpenAI API的交互
"""

import logging
import base64
import asyncio
import random
import contextlib
from typing import Union, List, Dict
from openai import AsyncOpenAI, APITimeoutError
from anyio import move_on_after

logger = logging.getLogger(__name__)

def calculate_backoff_delay(retry: int, base_delay: float = 1.0, jitter: float = 0.1) -> float:
    """
    计算指数退避延迟时间
    
    Args:
        retry: 当前重试次数
        base_delay: 基础延迟时间（秒）
        jitter: 随机抖动范围（0-1之间）
        
    Returns:
        float: 计算得到的延迟时间（秒）
    """
    delay = base_delay * (2 ** retry)
    jitter_amount = delay * jitter
    actual_delay = delay + random.uniform(-jitter_amount, jitter_amount)
    return max(base_delay, actual_delay)

class LLMConnector:
    """OpenAI API 连接器"""
    
    def __init__(self, openai_api_key: str):
        """初始化连接器"""
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self._closed = False
        self._closing = False
        self._close_event = asyncio.Event()

    async def ask_openai(
        self, 
        query: str, 
        model: str = "gpt-4", 
        temperature: float = 0.7, 
        max_tokens: int = 500
    ) -> str:
        """向OpenAI发送问题并获取回答"""
        if self._closed:
            raise RuntimeError("Connector is closed")
            
        try:
            response = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": query}
                ],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to query OpenAI: {str(e)}")
            raise

    async def create_image(
        self, 
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
        timeout: float = 60.0,
        max_retries: int = 3
    ) -> List[Dict[str, Union[str, bytes]]]:
        """使用 DALL·E 生成图像"""
        if self._closed:
            raise RuntimeError("Connector is closed")
            
        current_retry = 0
        last_error = None
        
        while current_retry <= max_retries:
            with move_on_after(timeout) as scope:
                try:
                    response = await self.client.images.generate(
                        model=model,
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        n=n,
                        response_format="url" # 改为获取url
                    )
                    
                    # 转换响应格式返回url和图片数据
                    image_data_list = []
                    for image in response.data:
                        image_data = {
                            "url": image.url,  # 原图URL
                            "media_type": "image/png"
                        }
                        image_data_list.append(image_data)
                    
                    if current_retry > 0:
                        logger.info(
                            f"在第 {current_retry + 1} 次尝试后成功生成图像"
                            f"（已消耗 {timeout * (current_retry + 1)} 秒）"
                        )
                    
                    return image_data_list
                    
                except Exception as e:
                    if not isinstance(e, asyncio.TimeoutError):
                        logger.error(f"生成图像失败: {str(e)}")
                        raise
                    
            if scope.cancel_called:
                last_error = asyncio.TimeoutError("Request timed out")
                current_retry += 1
                
                if current_retry <= max_retries:
                    delay = calculate_backoff_delay(current_retry)
                    logger.warning(
                        f"请求超时，将在 {delay:.2f} 秒后进行第 {current_retry} "
                        f"次重试（共 {max_retries} 次）..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break
        
        total_time = sum(calculate_backoff_delay(i) for i in range(current_retry))
        error_msg = (
            f"在 {max_retries} 次尝试（共耗时 {total_time:.2f} 秒）后仍然超时。"
            f"最后一次错误: {str(last_error)}"
        )
        logger.error(error_msg)
        raise TimeoutError(error_msg)

    async def close(self, timeout: float = 10.0) -> None:
        """关闭连接器"""
        if self._closed:
            logger.debug("Connector already closed")
            return
            
        if self._closing:
            logger.warning("Connector is already closing")
            await self._close_event.wait()
            return
            
        self._closing = True
        logger.info("Closing LLM connector...")
        
        try:
            with move_on_after(timeout) as scope:
                close_attempts = [
                    self._close_client_direct,
                    self._close_http_session,
                    self._close_connection_pools
                ]
                
                for attempt in close_attempts:
                    try:
                        await attempt()
                    except Exception as e:
                        logger.warning(f"Error in close attempt: {e}")
                        
            if scope.cancel_called:
                logger.error(f"Connector close timed out after {timeout} seconds")
                raise TimeoutError("Failed to close connector within timeout period")
                
        except Exception as e:
            logger.error(f"Error closing connector: {e}")
            raise
        finally:
            self._closed = True
            self._closing = False
            self._close_event.set()
            logger.info("LLM connector closed")
            
    async def _close_client_direct(self) -> None:
        """尝试直接关闭客户端"""
        if hasattr(self.client, 'close') and callable(self.client.close):
            await self.client.close()
            logger.debug("Closed OpenAI client directly")
            
    async def _close_http_session(self) -> None:
        """尝试关闭HTTP会话"""
        if hasattr(self.client, 'aiohttp_session') and self.client.aiohttp_session:
            await self.client.aiohttp_session.close()
            logger.debug("Closed aiohttp session")
            
    async def _close_connection_pools(self) -> None:
        """尝试关闭所有连接池"""
        if hasattr(self.client, '_pools'):
            for pool in self.client._pools.values():
                with contextlib.suppress(Exception):
                    await pool.close()
            logger.debug("Closed connection pools")