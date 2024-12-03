"""
MCP Server OpenAI 图像处理工具模块
处理图像压缩和格式转换
"""

import logging
from io import BytesIO
from PIL import Image
from typing import Tuple, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def managed_image(image_data: bytes):
    """
    安全管理图像资源的context manager
    
    Args:
        image_data: 原始图像数据
    """
    bio = BytesIO(image_data)
    img = Image.open(bio)
    try:
        yield img
    finally:
        img.close()
        bio.close()

@contextmanager
def managed_bytesio():
    """安全管理BytesIO资源的context manager"""
    bio = BytesIO()
    try:
        yield bio
    finally:
        bio.close()

def binary_search_quality(img: Image.Image, format: str, target_size: int, min_quality: int = 30) -> Tuple[bytes, int]:
    """
    使用二分查找算法确定最佳压缩质量
    
    Args:
        img: PIL 图像对象
        format: 图像格式 ('JPEG' 或 'PNG')
        target_size: 目标文件大小（字节）
        min_quality: 最小可接受质量
        
    Returns:
        Tuple[bytes, int]: 压缩后的数据和使用的质量值
    """
    low = min_quality
    high = 95
    best_data = None
    best_quality = high
    
    while low <= high:
        current_quality = (low + high) // 2
        
        with managed_bytesio() as bio:
            if format == 'PNG':
                img.save(bio, format=format, optimize=True)
            else:
                img.save(bio, format=format, quality=current_quality, optimize=True)
                
            data = bio.getvalue()
            size = len(data)
            
            if size <= target_size:
                best_data = data
                best_quality = current_quality
                low = current_quality + 1
            else:
                high = current_quality - 1
            
    if best_data is None:
        with managed_bytesio() as bio:
            if format == 'PNG':
                img.save(bio, format=format, optimize=True)
            else:
                img.save(bio, format=format, quality=min_quality, optimize=True)
            best_data = bio.getvalue()
            
    return best_data, best_quality

def get_optimal_dimensions(width: int, height: int, target_width: int = 1024) -> Tuple[int, int]:
    """
    计算保持宽高比的最佳尺寸
    
    Args:
        width: 原始宽度
        height: 原始高度
        target_width: 目标最大宽度
        
    Returns:
        Tuple[int, int]: 新的宽度和高度
    """
    if width <= target_width:
        return width, height
        
    ratio = target_width / width
    return target_width, int(height * ratio)

def compress_image_data(image_data: bytes, max_size: int = 512 * 1024) -> tuple[bytes, str]:
    """
    压缩图像数据，目标大小为512KB。使用高级压缩算法，尽量保持图像质量。
    
    Args:
        image_data (bytes): 原始图像数据
        max_size (int): 最大目标大小，默认512KB
        
    Returns:
        tuple[bytes, str]: 压缩后的数据和MIME类型
    """
    logger.debug(f"Original image size: {len(image_data)} bytes")
    
    try:
        if len(image_data) <= max_size:
            logger.debug(f"Image already within size limit")
            return image_data, 'image/png'

        with managed_image(image_data) as img:
            # 调整图像尺寸（如果需要）
            if img.width > 1024 or img.height > 1024:
                new_width, new_height = get_optimal_dimensions(img.width, img.height)
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.debug(f"Resized image to {new_width}x{new_height}")
                
            # 选择最佳格式和压缩设置
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # 对于带透明度的图像，使用PNG格式
                with managed_bytesio() as bio:
                    img.save(bio, format='PNG', optimize=True)
                    final_data = bio.getvalue()
                    mime_type = 'image/png'
                
                # 如果PNG太大，转换为JPEG（背景为白色）
                if len(final_data) > max_size:
                    logger.debug("Converting transparent PNG to JPEG with white background")
                    with managed_bytesio() as bio:
                        background = Image.new('RGB', img.size, 'white')
                        if img.mode == 'RGBA':
                            background.paste(img, mask=img.split()[3])
                        else:
                            background.paste(img)
                        
                        final_data, quality = binary_search_quality(background, 'JPEG', max_size)
                        logger.debug(f"Compressed JPEG (quality={quality})")
                        background.close()
                        mime_type = 'image/jpeg'
            else:
                # 对于不带透明度的图像，优先使用JPEG
                final_data, quality = binary_search_quality(img, 'JPEG', max_size)
                logger.debug(f"Compressed JPEG (quality={quality})")
                mime_type = 'image/jpeg'
                
            logger.debug(f"Final image size: {len(final_data)} bytes, format: {mime_type}")
            return final_data, mime_type
            
    except Exception as e:
        logger.error(f"Image compression failed: {str(e)}", exc_info=True)
        raise