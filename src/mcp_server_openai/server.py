import asyncio
import logging
import sys
import base64
from typing import Optional

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.shared.session import BaseSession

from .llm import LLMConnector

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 增加最大消息大小限制到32MB
MAX_MESSAGE_SIZE = 32 * 1024 * 1024

def create_session(*args, **kwargs) -> BaseSession:
    """创建一个自定义的会话，支持更大的消息大小"""
    session = BaseSession(*args, **kwargs)
    # 修改会话的消息大小限制
    if hasattr(session, '_write_stream'):
        session._write_stream._max_buffer_size = MAX_MESSAGE_SIZE
    return session

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
                description="使用 DALL·E 生成图像，直接在对话中显示",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "图像描述"},
                        "model": {"type": "string", "default": "dall-e-3", "enum": ["dall-e-3", "dall-e-2"]},
                        "size": {"type": "string", "default": "1024x1024", "enum": ["1024x1024", "512x512", "256x256"]},
                        "quality": {"type": "string", "default": "standard", "enum": ["standard", "hd"]},
                        "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10},
                        "timeout": {
                            "type": "number",
                            "default": 60.0,
                            "minimum": 30.0,
                            "maximum": 300.0,
                            "description": "请求超时时间（秒）"
                        },
                        "max_retries": {
                            "type": "integer",
                            "default": 3,
                            "minimum": 0,
                            "maximum": 5,
                            "description": "超时后最大重试次数"
                        }
                    },
                    "required": ["prompt"]
                }
            )
        ]

    @server.call_tool()
    async def handle_tool_call(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent]:
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
                timeout = arguments.get("timeout", 60.0)
                max_retries = arguments.get("max_retries", 3)
                
                status_message = (
                    f'正在生成图像，超时时间设置为 {timeout} 秒'
                    f'{"，最多重试 " + str(max_retries) + " 次" if max_retries > 0 else ""}...'
                )
                
                # 首先发送状态消息
                response_contents = [types.TextContent(type="text", text=status_message)]
                
                try:
                    # 尝试生成图像
                    image_data_list = await connector.create_image(
                        prompt=arguments["prompt"],
                        model=arguments.get("model", "dall-e-3"),
                        size=arguments.get("size", "1024x1024"),
                        quality=arguments.get("quality", "standard"),
                        n=arguments.get("n", 1),
                        timeout=timeout,
                        max_retries=max_retries
                    )

                    if server.request_context and hasattr(server.request_context.meta, 'progressToken'):
                        progress_token = server.request_context.meta.progressToken
                        try:
                            # 发送完成进度
                            await server.request_context.session.send_notification(
                                types.ProgressNotification(
                                    method="notifications/progress",
                                    params=types.ProgressNotificationParams(
                                        progressToken=progress_token,
                                        progress=100,
                                        total=100
                                    )
                                )
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send progress notification: {e}")
                    
                    # 添加生成完成的消息
                    response_contents.append(
                        types.TextContent(
                            type="text",
                            text='已生成 {} 张图像，描述为："{}"'.format(
                                len(image_data_list),
                                arguments['prompt']
                            )
                        )
                    )
                    
                    # 分批处理图像内容以避免超出消息大小限制
                    for image_data in image_data_list:
                        try:
                            encoded_data = base64.b64encode(image_data["data"]).decode('utf-8')
                            response_contents.append(
                                types.ImageContent(
                                    type="image",
                                    data=encoded_data,
                                    mimeType=image_data["media_type"]
                                )
                            )
                        except Exception as e:
                            logger.error(f"Failed to process image data: {e}")
                            response_contents.append(
                                types.TextContent(
                                    type="text",
                                    text=f"处理图像数据时出错: {str(e)}"
                                )
                            )
                            
                    return response_contents
                    
                except asyncio.CancelledError:
                    logger.info("Request was cancelled")
                    return [types.TextContent(type="text", text="请求已取消")]
                except TimeoutError as e:
                    logger.error(f"Image generation timed out: {e}")
                    return [types.TextContent(
                        type="text",
                        text=f"错误: 生成图像请求超时。您可以尝试:\n1. 增加超时时间（timeout参数）\n2. 增加重试次数（max_retries参数）\n3. 简化图像描述\n\n详细错误: {str(e)}"
                    )]
                except Exception as e:
                    logger.error(f"Error during image generation: {e}")
                    return [types.TextContent(type="text", text=f"生成图像时出错: {str(e)}")]

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
                # 使用自定义会话创建函数
                await server.run(
                    read_stream, write_stream,
                    InitializationOptions(
                        server_name="openai-server",
                        server_version="0.3.2",
                        capabilities=server.get_capabilities(
                            notification_options=NotificationOptions(tools_changed=True),
                            experimental_capabilities={}
                        )
                    ),
                    session_factory=create_session
                )
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
    except Exception as e:
        logger.exception("服务器运行失败")
        sys.exit(1)

if __name__ == "__main__":
    main()