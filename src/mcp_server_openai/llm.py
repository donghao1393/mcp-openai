import asyncio
import logging
from typing import Optional
from openai import OpenAI
import base64

logger = logging.getLogger(__name__)

class LLMConnector:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    async def ask_openai(
        self,
        query: str,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        try:
            response = await asyncio.to_thread(
                lambda: self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": query}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API call failed: {str(e)}")
            raise

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid"
    ) -> str:
        try:
            response = await asyncio.to_thread(
                lambda: self.client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    style=style,
                    response_format="b64_json"
                )
            )
            # 返回base64编码的图片数据
            return response.data[0].b64_json
        except Exception as e:
            logger.error(f"DALL-E API call failed: {str(e)}")
            raise