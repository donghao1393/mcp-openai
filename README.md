# OpenAI MCP 服务器

[前面的内容保持不变，直到配置步骤部分]

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

[中间内容保持不变，直到开发环境设置部分]

2. 直接运行服务：
```bash
# 使用 uv 运行
cd /path/to/mcp-openai
uv run mcp-openai
```

[后面的内容保持不变]