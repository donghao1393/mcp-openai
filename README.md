# OpenAI MCP 服务器

通过 MCP 协议直接从 Claude 调用 OpenAI 的模型进行对话和图像生成。支持在对话中直接显示生成的图像。

## 功能特点

- 支持与 GPT-4 和 GPT-3.5-turbo 模型对话
- 支持使用 DALL·E 2 和 DALL·E 3 生成图像，并直接在对话中显示
- 可配置的文本和图像生成参数
- 完整的异步支持
- 全面的错误处理和日志记录

## 设置方法

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "openai-server": {
      "command": "python",
      "args": ["-m", "src.mcp_server_openai.server"],
      "env": {
        "PYTHONPATH": "C:/path/to/your/mcp-server-openai",
        "OPENAI_API_KEY": "your-key-here"
      }
    }
  }
}
```

## 开发
```bash
git clone https://github.com/[your-username]/mcp-server-openai
cd mcp-server-openai
pip install -e .
```

## 可用工具

### 1. ask-openai
查询 OpenAI 的语言模型，支持以下参数：
- `query`: 您的问题或提示
- `model`: 选择 "gpt-4" 或 "gpt-3.5-turbo"
- `temperature`: 控制响应的随机性 (0-2)
- `max_tokens`: 最大响应长度 (1-4000)

### 2. create-image
使用 DALL·E 生成图像并直接在对话中显示，支持以下选项：
- `prompt`: 您想要生成的图像描述
- `model`: 选择 "dall-e-3" 或 "dall-e-2"
- `size`: 图像尺寸 ("1024x1024", "512x512", "256x256")
- `quality`: 图像质量 ("standard" 或 "hd")
- `n`: 生成图像的数量 (1-10)

## 更新说明

V0.3.0
- 改进了 DALL·E 图像生成功能，现在生成的图像会直接显示在对话中
- 优化了错误处理和响应格式
- 更新了文档和测试用例

## 测试
```python
# 在项目根目录运行测试
pytest -v test_openai.py -s
```

## 许可证
MIT 许可证