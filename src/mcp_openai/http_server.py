"""HTTP服务器模块,用于处理图片下载"""

import logging
from pathlib import Path
import asyncio
from aiohttp import web
import mimetypes

logger = logging.getLogger(__name__)

class ImageDownloadServer:
    """处理图片下载的HTTP服务器"""
    
    def __init__(self, image_dir: str = "original_images", host: str = "localhost", port: int = 8080):
        self.image_dir = Path(image_dir)
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/images/{filename}", self.handle_download)
        self._site = None
        self._runner = None
        
    async def handle_download(self, request: web.Request) -> web.Response:
        """处理下载请求"""
        filename = request.match_info["filename"]
        file_path = self.image_dir / filename
        
        try:
            if not file_path.exists() or not file_path.is_file():
                raise web.HTTPNotFound(text="文件不存在")
                
            # 确保路径在允许范围内
            if not file_path.resolve().is_relative_to(self.image_dir.resolve()):
                raise web.HTTPForbidden(text="访问被拒绝")
                
            # 获取文件类型
            content_type, _ = mimetypes.guess_type(str(file_path))
            if not content_type:
                content_type = "application/octet-stream"
                
            # 设置响应头,使浏览器下载文件而不是显示
            headers = {
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
            
            return web.FileResponse(file_path, headers=headers)
            
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"下载处理错误: {e}", exc_info=True)
            raise web.HTTPInternalServerError(text="服务器内部错误")
            
    async def start(self):
        """启动服务器"""
        try:
            logger.info(f"启动HTTP下载服务器 {self.host}:{self.port}")
            self._runner = web.AppRunner(self.app)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self.host, self.port)
            await self._site.start()
        except Exception as e:
            logger.error(f"启动HTTP服务器失败: {e}", exc_info=True)
            raise
            
    async def stop(self):
        """停止服务器"""
        try:
            if self._site:
                await self._site.stop()
            if self._runner:
                await self._runner.cleanup()
        except Exception as e:
            logger.error(f"停止HTTP服务器失败: {e}", exc_info=True)
            raise