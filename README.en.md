# OpenAI MCP Server

A MCP server implementation for direct interaction with OpenAI models through Claude. Supports text and image generation, with built-in image display, original image download links, and configurable timeout/retry mechanisms.

## Architecture Design

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

- Support for GPT-4 and GPT-3.5-turbo models
- Adjustable temperature and response length
- Streaming response support

### Image Generation

- Support for DALL·E 2 and DALL·E 3
- Smart image display:
  - Compressed images in chat
  - Original image download links
- Multiple size options:
  - DALL·E 2/3 common: 1024x1024, 512x512, 256x256
  - DALL·E 3 exclusive: 1792x1024 (landscape), 1024x1792 (portrait)
- HD quality option (DALL·E 3)
- Generation progress feedback
- Batch generation support (up to 10 images)
- Configurable timeout and retry mechanisms

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

## Setup

### Environment

We use uv for dependency management, offering faster package installation and dependency resolution. If you haven't installed uv, refer to the [official documentation](https://github.com/astral-sh/uv).

### Configuration Steps

1. Clone and setup:

```bash
git clone https://github.com/donghao1393/mcp-openai
cd mcp-openai

# Create and activate venv with uv
uv venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .
```

2. Add server config to `claude_desktop_config.json`:

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

OpenAI language model interaction:

- `query`: Your question or prompt
- `model`: "gpt-4" or "gpt-3.5-turbo"
- `temperature`: Randomness control (0-2)
- `max_tokens`: Response length (1-4000)

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

DALL·E image generation with compressed display and original download links:

- `prompt`: Image description
- `model`: "dall-e-3" or "dall-e-2"
- `size`: Image dimensions:
  - DALL·E 3: "1024x1024" (square), "1792x1024" (landscape), "1024x1792" (portrait)
  - DALL·E 2: "1024x1024", "512x512", "256x256" only
- `quality`: "standard" or "hd" (DALL·E 3 only)
- `n`: Number of images (1-10)

Example:

```python
# Landscape image
images = await client.create_image(
    prompt="A wolf running under moonlight",
    model="dall-e-3",
    size="1792x1024",
    quality="hd",
    n=1
)

# Portrait image
images = await client.create_image(
    prompt="An ancient lighthouse",
    model="dall-e-3",
    size="1024x1792",
    quality="standard",
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

1. Startup Issues

   - Check virtual environment activation
   - Verify dependency installation
   - Confirm PYTHONPATH setting
   - Validate OpenAI API key
2. Runtime Errors

   - ModuleNotFoundError: Check PYTHONPATH and dependencies
   - ImportError: Use `uv pip list` to verify packages
   - Startup failure: Check Python version (>=3.10)

### Performance Tips

1. For Complex Image Generation:

   - Increase timeout for DALL·E 3
   - Adjust max_retries
   - Simplify image descriptions
   - Consider DALL·E 2 for faster response
2. Batch Processing:

   - Allow 60 seconds per image
   - Use appropriate concurrency control
   - Implement request queuing

## Version History

### V0.4.0 (Current)

- Refactored image generation to use OpenAI native URLs
- Added original image download links
- Optimized image compression workflow
- Added DALL·E 3 landscape/portrait sizes
- Added uv package manager support
- Improved async operation stability
- Enhanced error handling

### V0.3.1

- Added configurable timeout and retry
- Optimized image generation error handling
- Enhanced user feedback detail

### V0.3.0

- Implemented in-chat image display
- Optimized error handling and response format
- Introduced anyio-based async framework

## License

MIT License
