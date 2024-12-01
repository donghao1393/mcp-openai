# OpenAI MCP 服务器

通过 MCP 协议直接从 Claude 调用 OpenAI 的模型进行对话和图像生成。支持在对话中直接显示生成的图像，并提供可配置的超时和重试机制。

## 功能特点

此服务器提供与 OpenAI 服务的深度集成，包括文本生成和图像创建功能。所有功能都经过优化，支持直接在对话界面中展示结果，并提供灵活的配置选项。

在文本生成方面，服务器支持与 GPT-4 和 GPT-3.5-turbo 模型的交互，允许用户调整温度和响应长度等参数。

在图像生成方面，服务器提供了 DALL·E 2 和 DALL·E 3 的完整支持，包括：
- 直接在对话中显示生成的图像
- 可配置的超时时间和重试机制
- 多种图像尺寸和质量选项
- 批量图像生成能力

## 设置方法

### 环境准备
我们使用 uv 作为依赖管理工具，它提供了更快的包安装和依赖解析速度。如果你还没有安装 uv，可以参考[官方文档](https://github.com/astral-sh/uv)进行安装。

### 配置步骤

1. 克隆仓库并设置环境：
```bash
git clone https://github.com/[your-username]/mcp-server-openai
cd mcp-server-openai

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
        "/Users/donghao/Documents/mcp/my-mcp-server-openai",
        "run",
        "mcp-server-openai"
      ],
      "env": {
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## 开发

### 开发环境设置

1. 创建开发环境：
```bash
# 创建和激活虚拟环境
uv venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 安装开发依赖
uv pip install -e .
```

2. 直接运行服务：
```bash
# 使用 uv 运行
cd /path/to/your/mcp-server-openai
uv run mcp-server-openai
```

### 开发工具推荐

- VS Code 或 PyCharm 作为 IDE
- `pylint` 和 `black` 用于代码质量检查和格式化
- `pytest` 用于单元测试

## 可用工具

### 1. ask-openai
此工具提供与 OpenAI 语言模型的交互功能，支持以下参数：
- `query`: 您的问题或提示
- `model`: 可选择 "gpt-4" 或 "gpt-3.5-turbo"
- `temperature`: 控制响应的随机性，范围为 0-2
- `max_tokens`: 最大响应长度，范围为 1-4000

### 2. create-image
此工具提供 DALL·E 图像生成功能，支持以下参数：
- `prompt`: 您想要生成的图像描述
- `model`: 可选择 "dall-e-3" 或 "dall-e-2"
- `size`: 图像尺寸，可选 "1024x1024"、"512x512" 或 "256x256"
- `quality`: 图像质量，可选 "standard" 或 "hd"
- `n`: 生成图像的数量，范围为 1-10
- `timeout`: 请求超时时间（秒），默认值为 60 秒，可设置范围为 30-300 秒
- `max_retries`: 超时后的最大重试次数，默认值为 3，可设置范围为 0-5

## 错误处理

本服务器实现了完善的错误处理机制，特别是对于复杂的图像生成任务：

1. 请求超时处理：当图像生成请求超过设定时间时，系统会自动进行重试。
2. 重试机制：在遇到超时时，系统会根据配置的 max_retries 参数进行多次尝试。
3. 用户反馈：在请求过程中，系统会提供清晰的状态更新，包括重试次数和剩余尝试次数。
4. 错误提示：当所有重试都失败时，系统会提供详细的错误信息和改进建议。

## 更新说明

V0.3.2
- 添加了 uv 包管理器支持
- 优化了项目结构，添加了 __main__.py 入口
- 更新了文档，增加了 uv 相关的设置和使用说明

V0.3.1
- 添加了可配置的超时和重试机制
- 优化了图像生成的错误处理流程
- 增强了用户反馈信息的详细程度
- 改进了图像生成状态的实时反馈

V0.3.0
- 实现了图像直接显示在对话中的功能
- 优化了错误处理和响应格式
- 更新了文档和测试用例

## 许可证
MIT 许可证

## 注意事项

1. 对于复杂的图像生成任务，建议适当增加 timeout 参数的值，特别是使用 DALL·E 3 模型时。
2. 如果遇到频繁超时，可以尝试：
   - 增加 timeout 参数的值
   - 调整 max_retries 参数
   - 简化图像描述
   - 考虑使用 DALL·E 2 模型，其响应时间通常更短

3. 在批量生成图像时，建议适当增加超时时间，每张图像预留至少 60 秒的处理时间。

## 故障排除

如果遇到服务启动问题，请检查：

1. 虚拟环境是否正确激活
2. 是否正确安装了所有依赖
3. PYTHONPATH 是否正确设置
4. OpenAI API key 是否有效

对于常见错误：

- `ModuleNotFoundError`: 检查 PYTHONPATH 设置和依赖安装
- `ImportError`: 使用 `uv pip list` 验证包安装状态
- 启动失败: 检查 Python 版本是否满足要求 (>=3.10)