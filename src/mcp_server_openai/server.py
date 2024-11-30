import asyncio
import logging
import sys
import base64
from typing import Optional
from io import BytesIO
from PIL import Image

import click
import mcp
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

from .llm import LLMConnector

# 配置日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

async def safe_send_notification(session, notification):
    """
    安全地发送通知，捕获并记录任何错误
    """
    try:
        await session.send_notification(notification)
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")

def compress_image_data(image_data: bytes, max_size: int = 512 * 1024) -> tuple[bytes, str]:
    """
    压缩图像数据，目标大小为512KB
    """
    logger.debug(f"Original image size: {len(image_data)} bytes")
    
    try:
        img = Image.open(BytesIO(image_data))
        
        # 如果原始大小已经足够小，直接返回PNG格式
        if len(image_data) <= max_size:
            bio = BytesIO()
            img.save(bio, format='PNG')
            final_data = bio.getvalue()
            logger.debug(f"Image already within size limit: {len(final_data)} bytes")
            return final_data, 'image/png'
        
        # 首先尝试调整图像尺寸
        max_dimension = 1024
        ratio = min(max_dimension / img.width, max_dimension / img.height)
        if ratio < 1:
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            
        quality = 95
        while quality > 30:
            bio = BytesIO()
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img.save(bio, format='PNG', optimize=True)
                mime_type = 'image/png'
            else:
                img.save(bio, format='JPEG', quality=quality, optimize=True)
                mime_type = 'image/jpeg'
            
            final_data = bio.getvalue()
            logger.debug(f"Compressed image size (quality={quality}): {len(final_data)} bytes")
            
            if len(final_data) <= max_size:
                break
                
            quality -= 10
            
        return final_data, mime_type
            
    except Exception as e:
        logger.error(f"Image compression failed: {str(e)}", exc_info=True)
        raise

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
                
                logger.info(f"Starting image generation with parameters: {arguments}")
                
                response_contents = [types.TextContent(type="text", text=status_message)]
                
                try:
                    if server.request_context and hasattr(server.request_context.meta, 'progressToken'):
                        progress_token = server.request_context.meta.progressToken
                        await safe_send_notification(
                            server.request_context.session,
                            types.ProgressNotification(
                                method="notifications/progress",
                                params=types.ProgressNotificationParams(
                                    progressToken=progress_token,
                                    progress=0,
                                    total=100
                                )
                            )
                        )

                    logger.debug("Calling OpenAI to generate image...")
                    image_data_list = await connector.create_image(
                        prompt=arguments["prompt"],
                        model=arguments.get("model", "dall-e-3"),
                        size=arguments.get("size", "1024x1024"),
                        quality=arguments.get("quality", "standard"),
                        n=arguments.get("n", 1),
                        timeout=timeout,
                        max_retries=max_retries
                    )
                    logger.debug(f"Received {len(image_data_list)} images from OpenAI")

                    if server.request_context and hasattr(server.request_context.meta, 'progressToken'):
                        await safe_send_notification(
                            server.request_context.session,
                            types.ProgressNotification(
                                method="notifications/progress",
                                params=types.ProgressNotificationParams(
                                    progressToken=progress_token,
                                    progress=100,
                                    total=100
                                )
                            )
                        )
                    
                    response_contents.append(
                        types.TextContent(
                            type="text",
                            text='已生成 {} 张图像，描述为："{}"'.format(
                                len(image_data_list),
                                arguments['prompt']
                            )
                        )
                    )
                    
                    for idx, image_data in enumerate(image_data_list, 1):
                        try:
                            logger.debug(f"Processing image {idx}/{len(image_data_list)}")
                            
                            # 只处理一个压缩版本的图像
                            compressed_data, mime_type = compress_image_data(image_data["data"])
                            encoded_data = base64.b64encode(compressed_data).decode('utf-8')
                            logger.debug(f"Image {idx}: Encoded size = {len(encoded_data)} bytes, MIME type = {mime_type}")

                            response_contents.append(
                                types.ImageContent(
                                    type="image",
                                    data=encoded_data,
                                    mimeType=mime_type
                                )
                            )

                            response_contents.append(
                                types.TextContent(
                                    type="text",
                                    text=f"\n已显示第 {idx} 张图片。\n{'-' * 50}"
                                )
                            )

                        except Exception as e:
                            error_msg = f"Failed to process image {idx}: {str(e)}"
                            logger.error(error_msg, exc_info=True)
                            response_contents.append(
                                types.TextContent(
                                    type="text",
                                    text=error_msg
                                )
                            )
                            
                    logger.info("Image generation and processing completed successfully")
                    return response_contents
                except asyncio.CancelledError as e:
                    logger.info("Request was cancelled by the client")
                    logger.debug(f"Cancellation details: {str(e)}", exc_info=True)
                    return [types.TextContent(type="text", text="请求已取消")]
                except TimeoutError as e:
                    error_msg = str(e)
                    logger.error(f"Image generation timed out: {error_msg}")
                    return [types.TextContent(
                        type="text",
                        text=f"错误: 生成图像请求超时。您可以尝试:\n1. 增加超时时间（timeout参数）\n2. 增加重试次数（max_retries参数）\n3. 简化图像描述\n\n详细错误: {error_msg}"
                    )]
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Error during image generation: {error_msg}", exc_info=True)
                    return [types.TextContent(type="text", text=f"生成图像时出错: {error_msg}")]

            raise ValueError(f"未知的工具: {name}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool call failed: {error_msg}", exc_info=True)
            return [types.TextContent(type="text", text=f"错误: {error_msg}")]

    return server

@click.command()
@click.option("--openai-api-key", envvar="OPENAI_API_KEY", required=True)
def main(openai_api_key: str):
    try:
        async def _run():
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                server = serve(openai_api_key)
                # 设置服务器的最大消息大小为32MB
                experimental_capabilities = {
                    "messageSize": {
                        "maxMessageBytes": 32 * 1024 * 1024
                    }
                }
                await server.run(
                    read_stream, write_stream,
                    InitializationOptions(
                        server_name="openai-server",
                        server_version="0.3.2",
                        capabilities=server.get_capabilities(
                            notification_options=NotificationOptions(tools_changed=True),
                            experimental_capabilities=experimental_capabilities
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