"""版本测试"""
import pytest
from mcp_server_openai.server import OpenAIServer

def test_version():
    """测试服务器版本号"""
    server = OpenAIServer()
    assert server.version == "0.4.0"