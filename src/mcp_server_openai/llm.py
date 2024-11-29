import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class LLMConnector:
    def __init__(self, openai_api_key: str):
        self.client = AsyncOpenAI(api_key=openai_api_key)

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
        n: int = 1
    ) -> list[str]:
        """
        使用 DALL·E 生成图像。
        
        参数:
            prompt (str): 图像描述
            model (str): 使用的 DALL·E 模型 ('dall-e-3' 或 'dall-e-2')
            size (str): 图像尺寸 ('1024x1024', '512x512', 或 '256x256')
            quality (str): 图像质量 ('standard' 或 'hd')
            n (int): 生成图像的数量 (1-10)
        
        返回:
            list[str]: 生成的图像 URL 列表
        """
        try:
            response = await self.client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=n
            )
            return [image.url for image in response.data]
        except Exception as e:
            logger.error(f"使用 DALL·E 生成图像失败: {str(e)}")
            raise