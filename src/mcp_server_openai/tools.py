"""
MCP Server OpenAI tools模块
包含工具定义和处理逻辑
"""

import logging
import base64
from typing import List

import mcp.types as types
from .notifications import NotificationManager, create_progress_notification
from .image_utils import compress_image_data

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
                    "n": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10}
                },
                "required": ["prompt"]
            }
        )
    ]

async def handle_ask_openai(connector, arguments: dict) -> List[types.TextContent]:
    """处理OpenAI问答请求"""
    try:
        response = await connector.ask_openai(
            query=arguments["query"],
            model=arguments.get("model", "gpt-4"),
            temperature=arguments.get("temperature", 0.7),
            max_tokens=arguments.get("max_tokens", 500)
        )
        return [types.TextContent(type="text", text=f"OpenAI 回答:\n{response}")]
    except Exception as e:
        logger.error(f"Error in ask_openai: {e}", exc_info=True)
        raise

async def handle_create_image(server, connector, arguments: dict) -> List[types.TextContent | types.ImageContent]:
    """处理图像生成请求"""
    session = server.request_context.session
    progress_token = server.request_context.meta.progressToken
    results: List[types.TextContent | types.ImageContent] = []
    
    # 创建通知管理器
    async with NotificationManager(session) as notification_mgr:
        try:
            # 1. 开始处理的提示
            status_message = '正在生成图像...'
            results.append(types.TextContent(type="text", text=status_message))
            
            if progress_token:
                await notification_mgr.send_notification(
                    await create_progress_notification(
                        progress_token=progress_token,
                        progress=0.0,  # 开始
                        total=100.0
                    )
                )
                
            # 2. 调用 OpenAI 生成图像
            logger.info(f"Starting image generation with parameters: {arguments}")
            image_data_list = await connector.create_image(
                prompt=arguments["prompt"],
                model=arguments.get("model", "dall-e-3"),
                size=arguments.get("size", "1024x1024"),
                quality=arguments.get("quality", "standard"),
                n=arguments.get("n", 1)
            )
            logger.debug(f"Received {len(image_data_list)} images from OpenAI")
            
            if progress_token:
                await notification_mgr.send_notification(
                    await create_progress_notification(
                        progress_token=progress_token,
                        progress=50.0,  # 生成完成
                        total=100.0
                    )
                )

            # 3. 处理返回的图像
            results.append(
                types.TextContent(
                    type="text",
                    text=f'已生成 {len(image_data_list)} 张图像，描述为："{arguments["prompt"]}"'
                )
            )

            # 4. 处理每张图片
            step_size = 40.0 / len(image_data_list)  # 剩余40%进度分配给图片处理
            for idx, image_data in enumerate(image_data_list, 1):
                logger.debug(f"Processing image {idx}/{len(image_data_list)}")
                
                # 压缩图像
                compressed_data, mime_type = compress_image_data(image_data["data"])
                encoded_data = base64.b64encode(compressed_data).decode('utf-8')
                
                # 添加图像到结果
                results.append(
                    types.ImageContent(
                        type="image",
                        data=encoded_data,
                        mimeType=mime_type
                    )
                )
                
                # 添加分隔信息
                results.append(
                    types.TextContent(
                        type="text",
                        text=f"\n已显示第 {idx} 张图片。\n{'-' * 50}"
                    )
                )
                
                if progress_token:
                    current_progress = 50.0 + step_size * idx
                    await notification_mgr.send_notification(
                        await create_progress_notification(
                            progress_token=progress_token,
                            progress=current_progress,
                            total=100.0
                        )
                    )

            # 5. 最终成功通知
            logger.info("Image generation and processing completed successfully")
            if progress_token:
                await notification_mgr.send_notification(
                    await create_progress_notification(
                        progress_token=progress_token,
                        progress=100.0,
                        total=100.0,
                        is_final=True
                    ),
                    shield=True  # 确保最终通知被发送
                )
                
            return results

        except Exception as e:
            error_msg = f"生成图像时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            results.append(types.TextContent(type="text", text=error_msg))
            
            # 发送错误状态通知
            if progress_token and not notification_mgr.is_closed:
                try:
                    await notification_mgr.send_notification(
                        await create_progress_notification(
                            progress_token=progress_token,
                            progress=0.0,
                            total=100.0,
                            is_final=True
                        ),
                        shield=True  # 确保错误通知被发送
                    )
                except Exception as notify_error:
                    logger.error(f"Failed to send error notification: {notify_error}")
                    
            return results