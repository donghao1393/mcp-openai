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
from anyio import fail_after

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
    # 指数退避
    delay = base_delay * (2 ** retry)
    # 添加随机抖动，避免多个请求同时重试
    jitter_amount = delay * jitter
    actual_delay = delay + random.uniform(-jitter_amount, jitter_amount)
    # 确保延迟不会小于基础延迟
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
        """
        向OpenAI发送问题并获取回答
        
        Args:
            query: 问题内容
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大令牌数
            
        Returns:
            str: 模型的回答
            
        Raises:
            RuntimeError: 如果连接器已关闭
        """
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
    ) -> List[Dict[str, Union[bytes, str]]]:
        """
        使用 DALL·E 生成图像并返回图像数据
        
        Args:
            prompt: 图像描述
            model: DALL·E 模型版本
            size: 图像尺寸
            quality: 图像质量
            n: 生成图像数量
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            
        Returns:
            List[Dict[str, Union[bytes, str]]]: 图像数据列表
            
        Raises:
            RuntimeError: 如果连接器已关闭
            TimeoutError: 如果请求超时且重试失败
        """
        if self._closed:
            raise RuntimeError("Connector is closed")
            
        current_retry = 0
        last_error = None
        
        while current_retry <= max_retries:
            try:
                with fail_after(timeout):
                    try:
                        response = await self.client.images.generate(
                            model=model,
                            prompt=prompt,
                            size=size,
                            quality=quality,
                            n=n,
                            response_format="b64_json"
                        )
                        
                        image_data_list = []
                        for image in response.data:
                            image_data = {
                                "data": base64.b64decode(image.b64_json),
                                "media_type": "image/png"
                            }
                            image_data_list.append(image_data)
                        
                        if current_retry > 0:
                            logger.info(
                                f"在第 {current_retry + 1} 次尝试后成功生成图像"
                                f"（已消耗 {timeout * (current_retry + 1)} 秒）"
                            )
                        
                        return image_data_list

                    except asyncio.TimeoutError:
                        raise APITimeoutError("Request timed out")
                
            except (APITimeoutError, asyncio.TimeoutError) as e:
                last_error = e
                current_retry += 1
                
                if current_retry <= max_retries:
                    # 计算下一次重试的延迟时间
                    delay = calculate_backoff_delay(current_retry)
                    logger.warning(
                        f"请求超时，将在 {delay:.2f} 秒后进行第 {current_retry} "
                        f"次重试（共 {max_retries} 次）..."
                    )
                    await asyncio.sleep(delay)
                    continue
                break

            except Exception as e:
                logger.error(f"生成图像失败: {str(e)}")
                raise
        
        total_time = sum(calculate_backoff_delay(i) for i in range(current_retry))
        error_msg = (
            f"在 {max_retries} 次尝试（共耗时 {total_time:.2f} 秒）后仍然超时。"
            f"最后一次错误: {str(last_error)}"
        )
        logger.error(error_msg)
        raise TimeoutError(error_msg)

    async def close(self, timeout: float = 10.0) -> None:
        """
        关闭连接器，清理资源
        
        Args:
            timeout: 关闭操作的超时时间（秒）
            
        Raises:
            TimeoutError: 如果关闭操作超时
            RuntimeError: 如果连接器已在关闭过程中
        """
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
            async with fail_after(timeout):
                # 尝试通过多种方式关闭客户端
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
                
        except asyncio.TimeoutError:
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