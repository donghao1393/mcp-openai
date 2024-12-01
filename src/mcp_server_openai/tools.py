"""
MCP Server OpenAI tools模块
包含工具定义和处理逻辑
"""

import logging
import asyncio
import base64
import gc
from typing import List, Optional, Any
from contextlib import contextmanager

import mcp.types as types
from anyio import CancelScope  # 修改：从anyio直接导入CancelScope
from .image_utils import compress_image_data
from .notifications import safe_send_notification, create_progress_notification

logger = logging.getLogger(__name__)

@contextmanager
def memory_tracker(operation_name: str):
    """
    跟踪内存使用的context manager
    
    Args:
        operation_name: 操作名称，用于日志记录
    """
    try:
        # 操作前强制进行垃圾回收
        gc.collect()
        yield
    finally:
        # 操作后再次强制进行垃圾回收
        gc.collect()
        logger.debug(f"Memory cleanup completed after {operation_name}")

def get_progress_token(server) -> Optional[str | int]:
    """
    安全地获取进度令牌
    
    Args:
        server: 服务器实例
        
    Returns:
        Optional[str | int]: 进度令牌，如果不可用则返回 None
    """
    try:
        if hasattr(server, 'request_context') and server.request_context:
            ctx = server.request_context
            if hasattr(ctx, 'meta') and ctx.meta and hasattr(ctx.meta, 'progressToken'):
                token = ctx.meta.progressToken
                if isinstance(token, (str, int)):
                    return token
    except Exception as e:
        logger.warning(f"Error getting progress token: {e}")
    return None

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

async def send_progress(session: Any, progress_token: str | int, progress: float, total: float = 100) -> None:
    """
    发送进度通知
    
    Args:
        session: 当前会话
        progress_token: 进度令牌
        progress: 当前进度（0-100）
        total: 总进度（默认100）
    """
    if not progress_token:
        return
        
    try:
        # 标准化进度值
        progress = max(0.0, min(float(progress), float(total)))
        
        # 创建并发送通知
        notification = await create_progress_notification(
            progress_token=progress_token,
            progress=progress,
            total=total
        )
        await safe_send_notification(session, notification)
    except Exception as e:
        logger.warning(f"Failed to send progress notification: {e}")

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
    timeout = arguments.get("timeout", 60.0)
    max_retries = arguments.get("max_retries", 3)
    results: List[types.TextContent | types.ImageContent] = []
    
    status_message = (
        f'正在生成图像，超时时间设置为 {timeout} 秒'
        f'{"，最多重试 " + str(max_retries) + " 次" if max_retries > 0 else ""}...'
    )
    
    logger.info(f"Starting image generation with parameters: {arguments}")
    results.append(types.TextContent(type="text", text=status_message))
    
    try:
        # 获取进度令牌
        progress_token = get_progress_token(server)
        session = getattr(server.request_context, 'session', None)

        if progress_token is not None and session is not None:
            # 开始生成：显示0%进度
            await send_progress(session, progress_token, 0)
        
        # 使用memory_tracker确保资源正确清理
        with memory_tracker("dall-e image generation"):
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

        # 更新生成完成进度
        if progress_token is not None and session is not None:
            await send_progress(session, progress_token, 50)

        results.append(
            types.TextContent(
                type="text",
                text='已生成 {} 张图像，描述为："{}"'.format(
                    len(image_data_list),
                    arguments['prompt']
                )
            )
        )
        
        # 使用CancelScope来保护图像处理过程
        try:
            # 修改：直接使用导入的CancelScope
            async with CancelScope(shield=True) as scope:
                for idx, image_data in enumerate(image_data_list, 1):
                    try:
                        logger.debug(f"Processing image {idx}/{len(image_data_list)}")
                        
                        with memory_tracker(f"image processing {idx}"):
                            # 压缩图像数据
                            compressed_data, mime_type = compress_image_data(image_data["data"])
                            encoded_data = base64.b64encode(compressed_data).decode('utf-8')
                            logger.debug(f"Image {idx}: Encoded size = {len(encoded_data)} bytes, MIME type = {mime_type}")

                            results.append(
                                types.ImageContent(
                                    type="image",
                                    data=encoded_data,
                                    mimeType=mime_type
                                )
                            )

                            results.append(
                                types.TextContent(
                                    type="text",
                                    text=f"\n已显示第 {idx} 张图片。\n{'-' * 50}"
                                )
                            )

                            # 更新进度：50% + (50% * 处理进度)
                            if progress_token is not None and session is not None:
                                progress = 50 + (50 * (idx / len(image_data_list)))
                                await send_progress(session, progress_token, progress)

                            # 在每张图片处理后进行垃圾回收
                            gc.collect()

                    except Exception as e:
                        error_msg = f"处理第 {idx} 张图片时出错: {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        results.append(
                            types.TextContent(type="text", text=error_msg)
                        )
                        
                # 全部完成：更新到100%进度
                if progress_token is not None and session is not None:
                    await send_progress(session, progress_token, 100)
                    
        except asyncio.CancelledError:
            logger.warning("Image processing was cancelled")
            raise
                
        logger.info("Image generation and processing completed successfully")
        return results
        
    except asyncio.CancelledError as e:
        logger.info("Request was cancelled by the client")
        logger.debug(f"Cancellation details: {str(e)}", exc_info=True)
        results.append(types.TextContent(type="text", text="请求已取消"))
        return results
        
    except TimeoutError as e:
        error_msg = str(e)
        logger.error(f"Image generation timed out: {error_msg}")
        results.append(
            types.TextContent(
                type="text",
                text=f"错误: 生成图像请求超时。您可以尝试:\n"
                     f"1. 增加超时时间（timeout参数）\n"
                     f"2. 增加重试次数（max_retries参数）\n"
                     f"3. 简化图像描述\n\n"
                     f"详细错误: {error_msg}"
            )
        )
        return results
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during image generation: {error_msg}", exc_info=True)
        results.append(
            types.TextContent(
                type="text",
                text=f"生成图像时出错: {error_msg}"
            )
        )
        return results
        
    finally:
        # 确保最终清理所有资源
        gc.collect()
        logger.debug("Final cleanup completed in handle_create_image")