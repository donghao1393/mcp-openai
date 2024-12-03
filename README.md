# OpenAI MCP 服务器

通过 MCP 协议直接从 Claude 调用 OpenAI 的模型进行对话和图像生成。支持在对话中直接显示生成的图像，并提供可配置的超时和重试机制。

## 架构设计

### 整体架构

```
                                    +-----------------+
                                    |                 |
                                    | Claude Desktop  |
                                    |                 |
                                    +--------+--------+
                                             |
                                             | MCP 协议
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

### 核心组件

1. **Server Core**

   - 负责 MCP 协议的实现
   - 处理请求路由和生命周期管理
   - 提供配置管理和错误处理
2. **Request Handler**

   - 处理具体的请求类型
   - 实现请求参数验证和转换
   - 管理请求超时和重试逻辑
3. **Notification Manager**

   - 管理进度通知的生命周期
   - 实现可靠的通知发送机制
   - 处理通知的取消和清理
4. **OpenAI Client**

   - 封装 OpenAI API 调用
   - 处理响应转换和错误处理
   - 实现 API 限流和重试策略

## 功能特点

### 文本生成

- 支持 GPT-4 和 GPT-3.5-turbo 模型
- 可调整温度和响应长度等参数
- 支持流式响应

### 图像生成

- 支持 DALL·E 2 和 DALL·E 3
- 直接在对话中显示生成的图像
- 可配置的超时时间和重试机制
- 多种图像尺寸和质量选项
- 批量图像生成能力

## 技术实现

### 异步处理

项目使用 `anyio` 作为异步运行时，支持在 asyncio 和 trio 上运行。主要的异步处理包括：

1. 请求处理

```python
async def handle_request(self, request: Request) -> Response:
    async with anyio.create_task_group() as tg:
        response = await tg.start(self._process_request, request)
        tg.cancel_scope.cancel()
    return response
```

2. 通知管理

```python
class NotificationManager:
    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
```

3. 超时控制

```python
async def with_timeout(timeout: float):
    async with anyio.move_on_after(timeout) as scope:
        yield scope
```

### 错误处理策略

1. 请求层错误处理

```python
try:
    response = await self.process_request(request)
except RequestError as e:
    return self.handle_request_error(e)
except Exception as e:
    return self.handle_unexpected_error(e)
```

2. API 调用重试机制

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

## 设置方法

### 环境准备

我们使用 uv 作为依赖管理工具，它提供了更快的包安装和依赖解析速度。如果你还没有安装 uv，可以参考[官方文档](https://github.com/astral-sh/uv)进行安装。

### 配置步骤

1. 克隆仓库并设置环境：

```bash
git clone https://github.com/donghao1393/mcp-openai
cd mcp-openai

# 使用 uv 创建和激活虚拟环境
uv venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
uv pip install -e .
```

2. 在 `claude_desktop_config.json` 中添加服务配置：

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

## 可用工具

### 1. ask-openai

此工具提供与 OpenAI 语言模型的交互功能：

- `query`: 您的问题或提示
- `model`: 可选择 "gpt-4" 或 "gpt-3.5-turbo"
- `temperature`: 控制响应的随机性，范围为 0-2
- `max_tokens`: 最大响应长度，范围为 1-4000

示例：

```python
response = await client.ask_openai(
    query="解释什么是量子计算",
    model="gpt-4",
    temperature=0.7,
    max_tokens=500
)
```

### 2. create-image

此工具提供 DALL·E 图像生成功能：

- `prompt`: 您想要生成的图像描述
- `model`: 可选择 "dall-e-3" 或 "dall-e-2"
- `size`: 图像尺寸，可选 "1024x1024"、"512x512" 或 "256x256"
- `quality`: 图像质量，可选 "standard" 或 "hd"
- `n`: 生成图像的数量，范围为 1-10

示例：

```python
images = await client.create_image(
    prompt="一只在月光下奔跑的狼",
    model="dall-e-3",
    size="1024x1024",
    quality="hd",
    n=1
)
```

## 开发指南

### 代码规范

1. **Python 代码风格**

   - 遵循 PEP 8 规范
   - 使用 black 进行代码格式化
   - 使用 pylint 进行代码质量检查
2. **异步编程规范**

   - 使用 async/await 语法
   - 正确处理异步上下文管理器
   - 适当使用任务组和取消作用域

### 开发工具推荐

- VS Code 或 PyCharm 作为 IDE
- `pylint` 和 `black` 用于代码质量检查和格式化
- `pytest` 用于单元测试

## 故障排除

### 常见问题

1. 服务启动问题

   - 检查虚拟环境是否正确激活
   - 验证所有依赖是否正确安装
   - 确认 PYTHONPATH 设置
   - 验证 OpenAI API key 有效性
2. 运行时错误

   - ModuleNotFoundError: 检查 PYTHONPATH 和依赖安装
   - ImportError: 使用 `uv pip list` 验证包安装状态
   - 启动失败: 检查 Python 版本 (>=3.10)

### 性能优化建议

1. 对于复杂的图像生成任务：

   - 适当增加 timeout 参数的值，特别是使用 DALL·E 3 时
   - 调整 max_retries 参数
   - 简化图像描述
   - 考虑使用 DALL·E 2，响应时间通常更短
2. 批量任务处理：

   - 每个图像预留至少 60 秒处理时间
   - 使用适当的并发控制
   - 实现请求队列和限流

## 版本历史

### V0.3.2 (当前版本)

- 添加了 uv 包管理器支持
- 优化了项目结构
- 改进了异步操作的稳定性
- 增强了错误处理机制

### V0.3.1

- 添加了可配置的超时和重试机制
- 优化了图像生成的错误处理流程
- 增强了用户反馈信息的详细程度

### V0.3.0

- 实现了图像直接显示在对话中的功能
- 优化了错误处理和响应格式
- 引入了基于 anyio 的异步处理框架

## 许可证

MIT 许可证
