# OpenAI MCP 服务器

[前面的内容保持不变...]

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

### 诊断步骤

1. 检查日志
```bash
# 查看日志
tail -f mcp_server_openai.log
```

2. 验证配置
```bash
# 检查环境变量
echo $OPENAI_API_KEY
echo $PYTHONPATH

# 检查配置文件
cat claude_desktop_config.json
```

3. 测试连接
```python
# 使用以下代码测试 API 连接
import openai
openai.api_key = "your-key-here"
response = await openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### 代码示例

#### 基本用法

1. 创建简单对话
```python
from mcp_server_openai.tools import handle_ask_openai

async def example_chat():
    response = await handle_ask_openai({
        "query": "What is Python?",
        "model": "gpt-3.5-turbo",
        "temperature": 0.7
    })
    print(response)
```

2. 生成图像
```python
from mcp_server_openai.tools import handle_create_image

async def example_image():
    response = await handle_create_image({
        "prompt": "A beautiful sunset over mountains",
        "model": "dall-e-3",
        "size": "1024x1024"
    })
    print(response)
```

#### 高级用法

1. 自定义超时和重试
```python
from mcp_server_openai.utils import with_retry_and_timeout

async def custom_request():
    async with with_retry_and_timeout(timeout=120, max_retries=3) as ctx:
        response = await handle_create_image({
            "prompt": "Complex scene with multiple elements",
            "model": "dall-e-3",
            "size": "1024x1024"
        })
    return response
```

2. 使用通知管理器
```python
from mcp_server_openai.notifications import NotificationManager

async def with_notifications():
    async with NotificationManager("task_id") as nm:
        await nm.send_progress("Starting image generation", 0)
        # 执行任务
        await nm.send_progress("Image generation complete", 100)
```

## 更新日志

### V0.3.2 (最新)
- 添加了 uv 包管理器支持
- 优化了项目结构，添加了 __main__.py 入口
- 更新了文档，增加了 uv 相关的设置和使用说明
- 改进了异步操作的稳定性
- 增强了错误处理机制

### V0.3.1
- 添加了可配置的超时和重试机制
- 优化了图像生成的错误处理流程
- 增强了用户反馈信息的详细程度
- 改进了图像生成状态的实时反馈

### V0.3.0
- 实现了图像直接显示在对话中的功能
- 优化了错误处理和响应格式
- 更新了文档和测试用例
- 引入了基于 anyio 的异步处理框架

## 开发路线图

### 即将推出
1. WebSocket 支持
   - 实时状态更新
   - 双向通信能力
   - 更好的连接管理

2. 高级重试策略
   - 智能退避算法
   - 条件重试机制
   - 自适应超时控制

3. 增强的监控
   - 详细的性能指标
   - 请求追踪能力
   - 资源使用统计

### 规划中
1. 集群支持
   - 负载均衡
   - 服务发现
   - 容错机制

2. 缓存优化
   - 响应缓存
   - 令牌缓存
   - 智能预取

## 社区与支持

### 获取帮助
1. GitHub Issues: 提交 bug 报告和功能请求
2. 项目 Discussions: 讨论使用经验和最佳实践
3. 邮件列表: 订阅更新通知和技术讨论

### 参与贡献
1. 提交代码: 通过 Pull Request 贡献代码
2. 改进文档: 帮助完善文档和示例
3. 分享经验: 在社区中分享使用心得

### 其他资源
1. 示例仓库: 查看完整的使用示例
2. 技术博客: 了解设计理念和实现细节
3. 视频教程: 观看入门指南和高级技巧

## 许可证
MIT 许可证 - 详见 [LICENSE](LICENSE) 文件