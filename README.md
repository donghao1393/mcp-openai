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
        "/path/to/your/mcp-server-openai",
        "run",
        "openai-service"
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
uv run openai-service
```

### 开发工具推荐

- VS Code 或 PyCharm 作为 IDE
- `pylint` 和 `black` 用于代码质量检查和格式化
- `pytest` 用于单元测试

[以下内容保持不变...]