# OpenAI MCP Server

MCP protocol integration that enables direct invocation of OpenAI models from Claude for conversations and image generation. Supports in-chat image display with configurable timeouts and retry mechanisms.

## Architecture

### Overall Architecture
```
                                    +-----------------+
                                    |                 |
                                    | Claude Desktop  |
                                    |                 |
                                    +--------+--------+
                                             |
                                             | MCP Protocol
                                             |
                              +-----------------------------+
                              |                             |
                              |    MCP Server (OpenAI)      |
                              |                             |
                              |  +---------------------+    |
                              |  |     Server Core     |    |
                              |  +---------------------+    |
                              |           |                 |
                              |  +---------------------+    |
                              |  |   Request Handler   |    |
                              |  +---------------------+    |
                              |           |                 |
                              |  +---------------------+    |
                              |  | Notification Manager|    |
                              |  +---------------------+    |
                              |           |                 |
                              |  +---------------------+    |
                              |  |    OpenAI Client    |    |
                              |  +---------------------+    |
                              |                             |
                              +-----------------------------+
                                             |
                                             |
                                    +-----------------+
                                    |                 |
                                    |    OpenAI API   |
                                    |                 |
                                    +-----------------+
```

### Core Components

1. **Server Core**
   - Implements the MCP protocol
   - Handles request routing and lifecycle management
   - Provides configuration management and error handling

2. **Request Handler**
   - Processes specific request types
   - Implements request parameter validation and transformation
   - Manages request timeouts and retry logic

3. **Notification Manager**
   - Manages notification lifecycle
   - Implements reliable notification delivery
   - Handles notification cancellation and cleanup

4. **OpenAI Client**
   - Encapsulates OpenAI API calls
   - Handles response transformation and error handling
   - Implements API rate limiting and retry strategies

## Features

### Text Generation
- Supports GPT-4 and GPT-3.5-turbo models
- Configurable temperature and response length parameters
- Stream response support

### Image Generation
- Supports DALL·E 2 and DALL·E 3
- Direct in-chat image display
- Configurable timeout and retry mechanisms
- Multiple image sizes and quality options
- Batch image generation capability

## Technical Implementation

### Asynchronous Processing
The project uses `anyio` as the async runtime, supporting both asyncio and trio. Key async processing includes:

1. Request Handling
```python
async def handle_request(self, request: Request) -> Response:
    async with anyio.create_task_group() as tg:
        response = await tg.start(self._process_request, request)
        tg.cancel_scope.cancel()
    return response
```

2. Notification Management
```python
class NotificationManager:
    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
```

3. Timeout Control
```python
async def with_timeout(timeout: float):
    async with anyio.move_on_after(timeout) as scope:
        yield scope
```

### Error Handling Strategy

1. Request Layer Error Handling
```python
try:
    response = await self.process_request(request)
except RequestError as e:
    return self.handle_request_error(e)
except Exception as e:
    return self.handle_unexpected_error(e)
```

2. API Call Retry Mechanism
```python
async def call_api_with_retry(self, func, *args, **kwargs):
    for attempt in range(self.max_retries):
        try:
            return await func(*args, **kwargs)
        except APIError as e:
            if not self.should_retry(e):
                raise
            await self.wait_before_retry(attempt)
```

## Setup Guide

### Environment Preparation
We use uv as the dependency management tool, offering faster package installation and dependency resolution. If you haven't installed uv, please refer to the [official documentation](https://github.com/astral-sh/uv).

### Configuration Steps

1. Clone repository and set up environment:
```bash
git clone https://github.com/donghao1393/mcp-openai
cd mcp-openai

# Create and activate virtual environment using uv
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .
```

2. Add service configuration to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "openai-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/mcp-openai",
        "run",
        "mcp-openai"
      ],
      "env": {
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## Available Tools

### 1. ask-openai
This tool provides interaction with OpenAI language models:
- `query`: Your question or prompt
- `model`: Choose between "gpt-4" or "gpt-3.5-turbo"
- `temperature`: Controls response randomness, range 0-2
- `max_tokens`: Maximum response length, range 1-4000

Example:
```python
response = await client.ask_openai(
    query="Explain quantum computing",
    model="gpt-4",
    temperature=0.7,
    max_tokens=500
)
```

### 2. create-image
This tool provides DALL·E image generation functionality:
- `prompt`: Description of the image you want to generate
- `model`: Choose between "dall-e-3" or "dall-e-2"
- `size`: Image size, options: "1024x1024", "512x512", or "256x256"
- `quality`: Image quality, options: "standard" or "hd"
- `n`: Number of images to generate, range 1-10

Example:
```python
images = await client.create_image(
    prompt="A wolf running under moonlight",
    model="dall-e-3",
    size="1024x1024",
    quality="hd",
    n=1
)
```

## Development Guide

### Code Standards
1. **Python Code Style**
   - Follow PEP 8 guidelines
   - Use black for code formatting
   - Use pylint for code quality checking

2. **Async Programming Standards**
   - Use async/await syntax
   - Properly handle async context managers
   - Appropriate use of task groups and cancel scopes

### Recommended Development Tools
- VS Code or PyCharm as IDE
- `pylint` and `black` for code quality checking and formatting
- `pytest` for unit testing

## Troubleshooting

### Common Issues
1. Service Startup Issues
   - Check virtual environment activation
   - Verify all dependencies installation
   - Confirm PYTHONPATH setting
   - Validate OpenAI API key

2. Runtime Errors
   - ModuleNotFoundError: Check PYTHONPATH and dependency installation
   - ImportError: Use `uv pip list` to verify package installation
   - Startup failure: Check Python version (>=3.10)

### Performance Optimization Tips
1. For complex image generation tasks:
   - Increase timeout parameter appropriately, especially with DALL·E 3
   - Adjust max_retries parameter
   - Simplify image descriptions
   - Consider using DALL·E 2 for faster response times

2. Batch Task Processing:
   - Allow at least 60 seconds processing time per image
   - Use appropriate concurrency control
   - Implement request queuing and rate limiting

## Version History

### V0.3.2 (Current)
- Added uv package manager support
- Optimized project structure
- Improved async operation stability
- Enhanced error handling mechanisms

### V0.3.1
- Added configurable timeout and retry mechanisms
- Optimized image generation error handling
- Enhanced user feedback information detail

### V0.3.0
- Implemented direct image display in conversations
- Optimized error handling and response format
- Introduced anyio-based async processing framework

## License
MIT License