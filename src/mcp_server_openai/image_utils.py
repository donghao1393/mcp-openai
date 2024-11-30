"""
MCP Server OpenAI 图像处理工具模块
处理图像压缩和格式转换
"""

import logging
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)

def compress_image_data(image_data: bytes, max_size: int = 512 * 1024) -> tuple[bytes, str]:
    """
    压缩图像数据，目标大小为512KB
    
    Args:
        image_data (bytes): 原始图像数据
        max_size (int): 最大目标大小，默认512KB
        
    Returns:
        tuple[bytes, str]: 压缩后的数据和MIME类型
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