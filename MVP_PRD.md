# 启量 Agent — MVP 第一阶段：脚本精炼引擎

## 1. 产品定位

启量 Agent 是一个**短视频自动化生产工具**。第一阶段（脚本精炼引擎）的核心功能是：用户输入短视频剧本 → AI 自动拆解出**钩子句、画面约束、带货金句**三个维度，为后续的 AI 视频生成提供结构化素材。

## 2. 技术架构

```
┌─────────────────────────────────────────┐
│                Streamlit                 │
│         极简 Web 界面（前端）              │
│  文本框输入 · 下拉菜单 · 侧边栏 · 结果展示  │
└─────────────────┬───────────────────────┘
                  │ Python 调用
┌─────────────────▼───────────────────────┐
│              LangChain                   │
│           AI 编排框架（后端）              │
│  提示词管理 · 链式调用 · JSON 解析 · 兜底  │
└─────────────────┬───────────────────────┘
                  │ OpenAI 兼容协议
┌─────────────────▼───────────────────────┐
│            DeepSeek API                  │
│           大模型推理（底层）               │
│  model: deepseek-chat · temperature: 0.1│
└─────────────────────────────────────────┘
```

### 技术选型理由

| 组件 | 选型 | 理由 |
|------|------|------|
| 前端 | Streamlit | 纯 Python 即可搭建 Web UI，无需 HTML/JS，十分钟出 MVP |
| 编排 | LangChain | 标准化大模型调用流程，Prompt 模板化，链式组合 |
| 模型 | DeepSeek API | OpenAI 兼容协议，中文理解能力强，JSON Mode 支持 |

## 3. 流水线模块

### 模块一：输入预处理层

- **入口**：Streamlit `text_area` 文本框
- **处理**：Python `re` 正则引擎
  - 清除不可见控制字符（保留换行符）
  - 压缩多余空行（≥3 行 → 2 行）
  - 去除首尾空白
- **出口**：干净文本送入 LangChain

### 模块二：动态参数选择

- **UI**：Streamlit `selectbox` 下拉菜单
- **参数名**：`Target_IP_Style`（视觉基调）
- **当前选项**：
  - `3D拟人化水果角色`
  - `美国真实街头风`
- **扩展**：后续可接入外部配置源动态加载

### 模块三：LangChain 调度与强约束输出

- **提示词管理**：系统提示词物理隔离在 `system_prompt.txt` 中，与代码解耦
- **Temperature**：0.1（低随机性，保证输出稳定）
- **JSON Mode**：通过 `response_format: {"type": "json_object"}` 强制开启
- **输出结构**：

```json
{
  "hook_sentences": ["..."],
  "visual_constraints": ["..."],
  "product_pitch": ["..."]
}
```

### 模块四：动态规则校验兜底

- 扫描大模型输出的 `visual_constraints` 字段
- 如果未包含用户选定的 `Target_IP_Style`，自动追加
- 保证后续视频生成阶段不会遗漏视觉基调

## 4. 文件结构

```
jak/
├── app.py              # 主程序（Streamlit + LangChain）
├── system_prompt.txt   # 系统提示词（物理隔离，可独立修改）
├── requirements.txt    # Python 依赖（可选）
├── MVP_PRD.md          # 本架构文档
├── CLAUDE.md           # 项目规则
├── .claude/            # Claude Code 配置
│   └── settings.json   # Hook 配置（flake8 自动检查）
└── .gitignore
```

## 5. 启动方式

```bash
pip install streamlit langchain langchain-openai
streamlit run app.py
```

浏览器访问 `http://localhost:8501`，填入 DeepSeek API Key 即可使用。

## 6. 后续阶段规划

| 阶段 | 功能 | 依赖 |
|------|------|------|
| 第二阶段 | AI 分镜生成 | 第一阶段 JSON 输出 |
| 第三阶段 | 图片/视频素材匹配 | 分镜 + 素材库 |
| 第四阶段 | 视频合成与渲染 | 素材 + 音频 |
| 第五阶段 | 批量发布与数据回传 | 各平台 API |
