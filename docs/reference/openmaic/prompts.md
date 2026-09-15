# OpenMAIC — Prompt 模式

> OpenMAIC 的 SKILL.md 定义了一套严格的 SOP 流程，其 prompt 工程模式值得 EduMind 参考。

## 1. SOP 驱动架构

OpenMAIC 使用 **分阶段 SOP (Standard Operating Procedure)** 管理复杂操作：

```
阶段 0: 选择模式 (托管 / 本地)
阶段 1: 克隆或复用已有仓库
阶段 2: 选择启动模式
阶段 3: 配置 Provider Key
阶段 4: 启动并验证服务
阶段 5: 生成课堂
```

每个阶段有独立的 reference 文件，包含该阶段的详细指令：
- `clone.md` — 仓库克隆流程
- `startup-modes.md` — 启动模式选择
- `provider-keys.md` — Key 配置指南
- `generate-flow.md` — 课堂生成完整流程
- `hosted-mode.md` — 托管模式说明

### EduMind 可借鉴的模式

对于 EduMind 的 8 个 Agent，可以采用类似的分阶段 prompt：

```python
# 示例: ProfileAgent 的 SOP 结构
class ProfileAgentSOP:
    phase_1 = "收集基础信息（年级、学科、兴趣）"
    phase_2 = "确认学习风格偏好"
    phase_3 = "评估当前知识水平"
    phase_4 = "生成 6 维画像"
    phase_5 = "用户确认 & 修正"
```

## 2. 确认驱动交互

SKILL.md 的核心规则：

```
核心规则:
- 每个阶段只推进一步
- 状态变更前必须确认
- 如果已存在本地状态，先展示再询问
- 不要让用户粘贴 API Key 到聊天中
- 引导用户自己编辑配置文件
```

### EduMind 应用

在对话画像采集 (ProfileAgent) 的 system prompt 中：

```
## 交互规则
1. 每次只问一个问题，等待用户回答
2. 在生成画像前，先展示已有推断并请用户确认
3. 不要一次性列出所有问题
4. 用户拒绝某项设定时，只修正该项，不重置整个画像
```

## 3. 错误恢复与降级策略

generate-flow.md 中的容错设计：

```
可靠性规则:
- 轮询失败一次 ≠ 重新提交 Job
- 网络瞬断 → 等 60s 重试同一 pollUrl
- 5xx 错误 → 不修改参数重试
- Auth/Provider 错误 → 告知用户修改服务端配置，不重试
- 轮询上限 10 分钟 → 告知用户稍后回来检查
```

### EduMind 应用

ReviewAgent 的二审机制也可以借鉴这个容错模式：

```python
# ReviewAgent 的容错逻辑
class ReviewAgent:
    MAX_RETRIES = 2

    async def review(self, content: GeneratedContent) -> ReviewResult:
        for attempt in range(self.MAX_RETRIES):
            result = await self._check(content)
            if result.passed:
                return result  # 通过
            if result.severe_hallucination:
                return self._reject(content)  # 严重幻觉 → 拒绝
            content = await self._retry_generation(result.feedback)  # 修正
        return self._fallback(content)  # 兜底
```

## 4. 模型无关设计

OpenMAIC 支持 15+ LLM Provider，通过统一接口隔离：

```typescript
// 统一 Provider 接口
interface LLMProvider {
  chat(messages: Message[]): Promise<Response>;
  streamChat(messages: Message[]): AsyncIterable<Chunk>;
}

// 通过配置文件切换
// server-providers.yml
providers:
  openai: { apiKey: "sk-..." }
  anthropic: { apiKey: "sk-ant-..." }
```

### EduMind 应用

虽然赛题要求用 讯飞星火，但应该设计成 Provider 可替换的架构：

```python
class BaseLLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[Message]) -> Response: ...
    @abstractmethod
    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[Chunk]: ...

class SparkProvider(BaseLLMProvider):
    # 讯飞星火实现

class OpenAIProvider(BaseLLMProvider):
    # OpenAI 实现（备用/测试）
```

## 5. 关键 Prompt 设计原则

从 SKILL.md 提取的设计原则：

| 原则 | 说明 |
|------|------|
| **最小权限** | 每个阶段只暴露该阶段需要的信息 |
| **显式确认** | 状态变更前必须用户确认 |
| **推荐优先** | 给出 2-3 选项，标注推荐项并说明理由 |
| **上下文传递** | 每个阶段引用上一阶段的产出 |
| **模式隔离** | 托管模式 / 本地模式走不同路径 |
| **有限轮询** | 异步 Job 设置轮询上限，避免死循环 |
