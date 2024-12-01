[previous content...]

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

[rest of the content...]