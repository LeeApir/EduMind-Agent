# MAIC-UI — Prompt 模式

> MAIC-UI 将所有 Prompt 集中在两个文件中管理，分为 Provider 通用 Prompt 和 Heavy Mode 专用 Prompt。这种集中管理模式值得 EduMind 参考。

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
        ├── STAGE2_LAYOUT_POLISH_PROMPT
        └── REFINEMENT_PROMPT
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

MAIC-UI 要求 LLM 输出严格的 JSON 结构：

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

**EduMind 应用**：每个 Agent 的输出应定义类似的 JSON Schema，便于 ReviewAgent 二审：

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

### 模式 D: 渐进式验证与精修

Heavy Mode 的分阶段生成 + 验证 + 精修模式：

```
生成 → 验证 → (失败 → 精修 → 验证) × 3 → 降级/回退
```

```python
# 从 heavy_generator.py 提取的验证循环
async def _execute_stage(self, stage_name, context, stage_func, 
                         validation_func, completed_stages, refinements):
    max_refinements = 3
    for attempt in range(max_refinements + 1):
        content = await stage_func(context)
        result = validation_func(content)
        if result.passed:
            return content
        if attempt < max_refinements:
            context['refinement_feedback'] = result.feedback
            content = await refinement_func(context, result.feedback)
        refinements[stage_name] += 1
    return None  # 触发降级
```

**EduMind 应用**：这正好对应 ReviewAgent 的 `最多退修 2 次 → 拒绝 + 兜底` 的机制。

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
5. 交互性：至少 3 个可控参数
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
| **集中管理** | 所有 Prompt 在 2 个 .py 文件中 | 按 Agent 拆分，但统一管理 |
| **结构化输出** | 严格的 JSON Schema | 每个 Agent 定义输出契约 |
| **画像注入** | 年级/兴趣注入 Prompt | 6 维画像作为全局上下文 |
| **多语言** | 中英文独立 Prompt + 排版规范 | 预留多语言接口 |
| **验证闭环** | 生成 → 验证 → 精修 → 重验证 | 生成 → ReviewAgent → 退修/通过 |
| **降级兜底** | 精修失败 → 降级到 Fast Mode | ReviewAgent 拒绝 → 兜底内容 |
| **缓存复用** | 成功生成结果缓存 | 高频资源预生成 + 缓存 |
