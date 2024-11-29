import logging
import base64
import asyncio
from typing import Union, List, Dict
from openai import AsyncOpenAI, APITimeoutError

logger = logging.getLogger(__name__)

class LLMConnector:
    def __init__(self, openai_api_key: str):
        self.client = AsyncOpenAI(
            api_key=openai_api_key,
            timeout=60.0  # 默认超时时间
        )

    async def ask_openai(self, query: str, model: str = "gpt-4", temperature: float = 0.7, max_tokens: int = 500) -> str:
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
        使用 DALL·E 生成图像并返回图像数据。
        
        参数:
            prompt (str): 图像描述
            model (str): 使用的 DALL·E 模型 ('dall-e-3' 或 'dall-e-2')
            size (str): 图像尺寸 ('1024x1024', '512x512', 或 '256x256')
            quality (str): 图像质量 ('standard' 或 'hd')
            n (int): 生成图像的数量 (1-10)
            timeout (float): 每次请求的超时时间（秒）
            max_retries (int): 超时后的最大重试次数
        
        返回:
            List[Dict[str, Union[bytes, str]]]: 包含图像数据和相关信息的字典列表
        
        异常:
            TimeoutError: 所有重试都失败后抛出
            Exception: 其他错误情况
        """
        current_retry = 0
        last_error = None
        retry_delay = 2  # 重试之间的延迟时间（秒）
        
        while current_retry <= max_retries:
            try:
                # 更新客户端超时设置
                self.client.timeout = timeout
                
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
                    logger.info(f"在第 {current_retry + 1} 次尝试后成功生成图像")
                
                return image_data_list
                
            except APITimeoutError as e:
                last_error = e
                current_retry += 1
                if current_retry <= max_retries:
                    logger.warning(f"请求超时，正在进行第 {current_retry} 次重试（共 {max_retries} 次）...")
                    await asyncio.sleep(retry_delay)
                continue
            except Exception as e:
                logger.error(f"生成图像失败: {str(e)}")
                raise
        
        error_msg = f"在 {max_retries} 次尝试后仍然超时。最后一次错误: {str(last_error)}"
        logger.error(error_msg)
        raise TimeoutError(error_msg)