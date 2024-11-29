"""
MCP OpenAI Server package
"""

__version__ = "0.1.0"

def get_version():
    return __version__

from .server import main, serve  # noqa
from .llm import LLMConnector  # noqa