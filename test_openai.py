import os
import pytest
from src.mcp_server_openai.llm import LLMConnector

@pytest.mark.asyncio
async def test_ask_openai():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("环境变量中未找到 OPENAI_API_KEY")
    
    connector = LLMConnector(api_key)
    print("\n测试 OpenAI API 调用...")
    response = await connector.ask_openai("你好！最近如何？")
    print(f"OpenAI 响应: {response[:50]}...")
    assert response and len(response) > 0

@pytest.mark.asyncio
async def test_create_image():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("环境变量中未找到 OPENAI_API_KEY")
    
    connector = LLMConnector(api_key)
    print("\n测试 DALL·E 图像生成...")
    urls = await connector.create_image(
        prompt="一个安静的山间日落景色",
        model="dall-e-3",
        size="1024x1024"
    )
    print(f"生成的图像 URL: {urls[0][:50]}...")
    assert urls and len(urls) > 0
    assert urls[0].startswith("https://")