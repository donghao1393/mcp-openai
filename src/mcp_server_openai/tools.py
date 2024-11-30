"""
MCP Server OpenAI tools模块
包含工具定义和处理逻辑
"""

import logging
import asyncio
import base64
from typing import List

import mcp.types as types
from .image_utils import compress_image_data
from .notifications import safe_send_notification

logger = logging.getLogger(__name__)

def get_tool_definitions() -> List[types.Tool]:
    """返回支持的工具列表"""
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

async def handle_ask_openai(connector, arguments: dict) -> List[types.TextContent]:
    """处理OpenAI问答请求"""
    response = await connector.ask_openai(
        query=arguments["query"],
        model=arguments.get("model", "gpt-4"),
        temperature=arguments.get("temperature", 0.7),
        max_tokens=arguments.get("max_tokens", 500)
    )
    return [types.TextContent(type="text", text=f"OpenAI 回答:\n{response}")]

async def handle_create_image(server, connector, arguments: dict) -> List[types.TextContent | types.ImageContent]:
    """处理图像生成请求"""
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