# MAIC-UI — Prompt 模式

> 2026-10-29 源码复核：以下两个文件是核心 Prompt 入口，不是全部提示词所在地；`read.py` 等服务还有内嵌提示词。核对版本为 `aad58ddcc2103058b4c2deffc48a3c13e2c64dd6`。Heavy 主执行点实际跳过验证，见下文模式 D。与 DeepTutor 的对照见[提示词专题](../deeptutor/prompts.md)。
>
> 本文中的“EduMind 应用”保留为早期设计建议，不代表当前 PRD 或已批准契约；画像字段不得凭空补齐，具体角色与修复上限以当前项目批准文件为准。

## 1. Prompt 组织架构

```
backend/src/services/
├── prompts/
│   └── ai_prompts.py          # 通用 Prompt (所有 Provider 复用)
│       ├── English Provider
│       │   ├── english_content_analysis_prompt()
│       │   ├── english_knowledge_card_prompt()
│       │   └── english_website_generation_prompt()
│       └── Anthropic Provider (中文)
│           ├── anthropic_content_analysis_prompt()
│           ├── anthropic_knowledge_card_prompt()
│           └── anthropic_website_generation_prompt()
└── templates/
    └── heavy_mode_prompts.py   # Heavy Mode 专用 Prompt
        ├── STAGE1_ALIGNED_SIMULATION_PROMPT
        ├── STAGE2_POLISH_PROMPT
        └── REFINEMENT_PROMPTS
```

### EduMind 可借鉴的结构

```python
# EduMind 建议的 Prompt 组织结构
backend/app/agents/
├── prompts/
│   ├── profile_prompts.py     # ProfileAgent 对话策略
│   ├── doc_prompts.py         # DocAgent 内容生成
│   ├── quiz_prompts.py        # QuizAgent 题目生成
│   ├── mindmap_prompts.py     # MindmapAgent 结构生成
│   ├── video_prompts.py       # VideoAgent 脚本生成
│   ├── code_prompts.py        # CodeAgent 代码生成
│   ├── review_prompts.py      # ReviewAgent 审核标准
│   └── path_prompts.py        # PathAgent 路径规划
└── templates/
    └── debate_prompts.py      # 辩论圆桌专用 Prompt
```

## 2. Prompt 设计模式

### 模式 A: 结构化 JSON 输出

MAIC-UI 的内容分析模板以自然语言要求 JSON 结构。下面是输出形状示例，不是提供商强制执行 JSON Schema 的证据：

```python
# 内容分析 Prompt 的输出格式要求
"""
Format your response as JSON:
{
    "main_topics": ["topic1", "topic2"],
    "key_concepts": ["concept1", "concept2", "concept3"],
    "learning_objectives": ["objective1", "objective2"],
    "prerequisite_knowledge": ["prereq1", "prereq2"],
    "difficulty_level": "beginner/intermediate/advanced",
    "target_grade_level": "K-12 grade level",
    "content_structure": [
        {
            "title": "Section Title",
            "page_start": 1,
            "page_end": 3,
            "topics": ["subtopic1", "subtopic2"]
        }
    ],
    "visual_elements": ["diagrams", "charts", "illustrations"],
    "subject_area": "Mathematics/Science/Language Arts/etc"
}
"""
```

**早期 EduMind 建议**：为各职责定义输出契约并配套程序校验；下面只是 JSON 形状示意，不是正式 JSON Schema，也不能单靠模型二审代替程序校验：

```python
# DocAgent 输出 Schema
{
    "title": "章节标题",
    "sections": [
        {
            "heading": "小节标题",
            "content": "Markdown 正文",
            "key_points": ["要点1", "要点2"],
            "examples": [{"description": "...", "code": "..."}]
        }
    ],
    "references": ["关联知识点1", "关联知识点2"],
    "difficulty": "beginner/intermediate/advanced"
}
```

### 模式 B: 用户画像注入

MAIC-UI 将用户画像直接注入 Prompt：

```python
def english_content_analysis_prompt(grade_level: str, interests: List[str]) -> str:
    interests_text = ", ".join(interests) if interests else "General learning"
    return f"""
        Analyze these educational PDF pages...

        User Profile:
        - Grade Level: {grade_level}
        - Interests: {interests_text}
        ...
    """
```

**EduMind 应用**：ProfileAgent 的 6 维画像作为全局上下文注入每个生成 Agent：

```python
# 每个生成 Agent 的 System Prompt 都包含画像上下文
SYSTEM_PROMPT_TEMPLATE = """
## 学习者画像
- 年级: {grade_level}
- 学科: {subject}
- 学习风格: {learning_style}
- 知识水平: {knowledge_level}
- 兴趣领域: {interests}
- 学习目标: {learning_goals}

## 当前任务
{task_description}

## 输出要求
{output_schema}
"""
```

### 模式 C: 多语言 Prompt 模式

MAIC-UI 对中英文使用不同的 Prompt + 排版规范：

```python
LANGUAGE_REQUIREMENTS_CN = """
**语言要求（重要）：**
- 所有用户可见内容必须使用简体中文
- HTML标签、CSS类名、JavaScript变量名使用英文
- 使用标准中文标点符号：。，；：！？（）【】
- 中文字体：'Source Han Sans CN', 'Microsoft YaHei', 'SimHei', sans-serif
"""

LANGUAGE_REQUIREMENTS_EN = """
**Language Requirements (IMPORTANT):**
- All user-visible content must be in English
- HTML tags, CSS class names, JavaScript variables in English
- Font: 'Inter', 'Segoe UI', 'Roboto', sans-serif
"""
```

**EduMind 应用**：考虑到赛题面向中国学生，默认中文，但预留英文接口：

```python
class LanguageConfig:
    zh = {
        "user_content_lang": "简体中文",
        "code_lang": "英文",
        "punctuation": "。，；：！？（）【】",
        "font": "'Source Han Sans CN', 'Microsoft YaHei', sans-serif"
    }
    en = {
        "user_content_lang": "English",
        "code_lang": "English",
        "punctuation": ". , ; : ! ? ( ) [ ]",
        "font": "'Inter', 'Segoe UI', sans-serif"
    }
```

### 模式 D: 两阶段生成与验证接线边界

Heavy Mode 模板表达了分阶段生成与精修意图，但当前固定版本的主执行点没有运行传入验证器。实际流程可概括为：

```
阶段生成 → 非空即按“验证通过”路径返回并缓存
空结果 / 异常 → 最多三次尝试 → 降级/回退
Stage 1 HTML → Stage 2 布局精修
```

```python
# heavy_generator.py::_execute_stage 的关键原文
# is_valid, issues = validation_func(html)
is_valid, issues = True, None
```

函数使用 `range(max_refinements)`，其中 `max_refinements = 3`，不是首次加三次。`get_refinement_prompt` 在该生成器中仅导入，执行循环未调用，也未将验证问题注入下一轮 context。因此不能把旧笔记中的“生成→验证→反馈精修”伪代码当作当前实际实现。[固定源码](https://github.com/THU-MAIC/MAIC-UI/blob/aad58ddcc2103058b4c2deffc48a3c13e2c64dd6/backend/src/services/html_generation/heavy_generator.py#L180)

**EduMind 应用建议**：可以参考阶段拆分，但真实校验和错误驱动修复必须另行实现并验证，不能从存在精修模板推断闭环已生效。

## 3. Heavy Mode Prompt 结构

两阶段 Prompt 的核心设计：

### Stage 1: 内容对齐的交互式模拟

```
目标: 创建 左过程展示 + 右交互模拟 的双栏布局

要求:
1. 左右双栏布局（核心设计）
2. 左侧面板 - 程序性过程展示
   - 步骤编号、标题、说明
   - 当前步骤高亮、已完成标记
3. 右侧面板 - 交互式模拟
   - Canvas/SVG 可视化
   - 控制面板（播放/暂停/重置/速度）
4. 内容对齐：左侧步骤变化 → 右侧模拟同步更新
5. 交互性：至少 2 个可调参数（模板要求，未证明运行时已验证）
```

### Stage 2: 布局精修

```
目标: 在 Stage 1 基础上优化视觉和用户体验

要求:
1. 视觉美化: 统一配色、动画过渡、响应式
2. 功能验证: 按钮可用、模拟正确、无 JS 错误
3. 内容检查: 准确性、完整性、适合目标年级
4. 性能优化: 初始加载 < 2s、交互响应 < 100ms
```

## 4. 关键设计原则

| 原则 | MAIC-UI 实现 | EduMind 可借鉴 |
|------|-------------|---------------|
| **集中管理** | 核心 Prompt 有集中入口，部分仍内嵌服务 | 按职责拆分并明确装配入口 |
| **结构化输出** | 模板要求 JSON 形状，不等于服务方强制 Schema | 输出契约配套程序校验 |
| **画像注入** | 年级/兴趣注入 Prompt | 6 维画像作为全局上下文 |
| **多语言** | 中英文独立 Prompt + 排版规范 | 预留多语言接口 |
| **验证闭环** | 有验证器和精修模板，但当前 Heavy 主执行点跳过验证 | 需验证程序检查、模型审核和修复实际执行 |
| **降级兜底** | 阶段生成失败 → 按实现降级/回退 | 拒绝与兜底应明确区分，并遵循批准契约 |
| **缓存复用** | 成功生成结果缓存 | 高频资源预生成 + 缓存 |
