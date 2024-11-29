import asyncio
import logging
import sys
from typing import Optional

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

from .llm import LLMConnector

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def serve(openai_api_key: str) -> Server:
    server = Server("openai-server")
    connector = LLMConnector(openai_api_key)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="ask-openai",
                description="向 OpenAI 助手模型提问",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "提问内容"},
                        "model": {"type": "string", "default": "gpt-4", "enum": ["gpt-4", "gpt-3.5-turbo"]},
                        "temperature": {"type": "number", "default": 0.7, "minimum": 0, "maximum": 2},
                        "max_tokens": {"type": "integer", "default": 500, "minimum": 1, "maximum": 4000}
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="create-image",
                description="使用 DALL·E 生成图像",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "图像描述"},
                        "model": {"type": "string", "default": "dall-e-3", "enum": ["dall-e-3", "dall-e-2"]},
                        "size": {"type": "string", "default": "1024x1024", "enum": ["1024x1024", "512x512", "256x256"]},
                        "quality": {"type": "string", "default": "standard", "enum": ["standard", "hd"]},
                        "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10}
                    },
                    "required": ["prompt"]
                }
            )
        ]

    @server.call_tool()
    async def handle_tool_call(name: str, arguments: dict | None) -> list[types.TextContent]:
        try:
            if not arguments:
                raise ValueError("未提供参数")

            if name == "ask-openai":
                response = await connector.ask_openai(
                    query=arguments["query"],
                    model=arguments.get("model", "gpt-4"),
                    temperature=arguments.get("temperature", 0.7),
                    max_tokens=arguments.get("max_tokens", 500)
                )
                return [types.TextContent(type="text", text=f"OpenAI 回答:\n{response}")]
            
            elif name == "create-image":
                image_urls = await connector.create_image(
                    prompt=arguments["prompt"],
                    model=arguments.get("model", "dall-e-3"),
                    size=arguments.get("size", "1024x1024"),
                    quality=arguments.get("quality", "standard"),
                    n=arguments.get("n", 1)
                )
                return [types.TextContent(
                    type="text", 
                    text="生成的图像链接:\n" + "\n".join(f"- {url}" for url in image_urls)
                )]

            raise ValueError(f"未知的工具: {name}")
        except Exception as e:
            logger.error(f"工具调用失败: {str(e)}")
            return [types.TextContent(type="text", text=f"错误: {str(e)}")]

    return server

@click.command()
@click.option("--openai-api-key", envvar="OPENAI_API_KEY", required=True)
def main(openai_api_key: str):
    try:
        async def _run():
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                server = serve(openai_api_key)
                await server.run(
                    read_stream, write_stream,
                    InitializationOptions(
                        server_name="openai-server",
                        server_version="0.2.0",  # 更新版本号
                        capabilities=server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={}
                        )
                    )
                )
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
    except Exception as e:
        logger.exception("服务器运行失败")
        sys.exit(1)

if __name__ == "__main__":
    main()