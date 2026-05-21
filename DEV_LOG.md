# 启量 Agent 开发日记

> 这本日记用大白话记录每一次核心代码改动背后的「思考过程」和「决策理由」。
> 目标读者：产品经理、非技术背景的项目 owner、未来接手维护的任何人。

---

## 2026-05-21：完成前后端全线总装 — 四阶段流水线集成

### 做了什么

将 `phase2_processor.py`、`phase3_multimodal.py` 和 `phase4_assembly.py` 三大独立模块的核心能力全部整合进 `app.py` 主程序，实现了从「输入剧本」到「最终装配方案」的完整一键式流水线。

### 集成架构

```
用户输入剧本
    │
    ▼
Phase 1: 脚本精炼 (原有的 app.py 逻辑)
    │  输出 hook_sentences / visual_constraints / product_pitch
    ▼
Phase 2: 翻译 + 分镜并发 (接入 phase2_processor.process_phase2_sync)
    │  输出 translated_pitches / storyboard_prompts
    ▼
Phase 3: TTS 配音 + 视觉分发路由 (接入 phase3_multimodal.batch_tts + visual_distribution_router)
    │  输出 TTS 音频文件 + 视频/图像素材（黄金 30 秒路由）
    │
    ├── [人机协作节点 1] 视觉素材审核 ← Streamlit checkbox 替代 terminal input()
    │
    ▼
Phase 4: 时间轴对齐 + 智能特效方案 (接入 phase4_assembly.build_timeline + generate_effects_plan)
    │  输出 Timeline JSON + 特效方案
    │
    ├── [人机协作节点 2] 特效方案审批 ← Streamlit radio 替代 terminal input()
    │
    ▼
最终输出：5 个 Tab 页展示全链路结果
```

### 关键技术决策

**1. Session State 驱动的流水线状态机**

Streamlit 的本质是「每次用户操作都重新执行整个脚本」。为了让四阶段不重复执行、人机协作节点能暂停等待，用 `st.session_state` 实现了 5 个状态的流水线：

| 状态 | 含义 | 触发下一步 |
|------|------|-----------|
| `idle` | 等待用户输入剧本 | 点击「启动全线流水线」 |
| `awaiting_review` | Phase 3 完成，等待品控 | 点击「确认品控结果」 |
| `awaiting_approval` | Phase 4 完成，等待审批 | 点击「确认提交」 |
| `complete` | 全线完成 | 点击「重置流水线」 |

**2. 人机协作的 Streamlit 化**

原来的 `human_review_interceptor()` 和 `human_final_approval()` 使用 Python 的 `input()` 函数阻塞终端等待输入——这在网页里根本用不了。改为纯 Streamlit 组件：

- **视觉审核**：`st.checkbox`（逐条确认采纳/驳回 + 驳回原因文本框）
- **特效审批**：`st.radio`（确认/修改/驳回三选一 + 修改意见文本框）

不直接调原函数，而是在 Streamlit 层重建了等效的交互逻辑。

**3. Tab 页展示全链路结果**

用 `st.tabs` 把四个阶段的输出 + 全链路 JSON 分别放在独立 Tab 里，方便老板做 Demo 时逐个展示。

**4. 数据格式桥接**

四个阶段之间的数据格式不完全一致，做了三处桥接：
- Phase 1 → Phase 2：给 `phase1_json` 补充 `script` 和 `target_ip_style` 字段
- Phase 2 → Phase 3：把 `storyboard_prompts`（字符串列表）转换为 `[{prompt, duration_seconds}]` 格式
- Phase 3 → Phase 4：TTS segments 补充 `text` 字段，视觉素材过滤掉品控驳回的条目

**5. `st.status` 进度反馈**

Phase 1~3 的自动执行阶段用 `st.status` 上下文管理器包裹，用户能看到每个阶段是成功还是失败，不再是黑盒等待。

### 为什么要总装而不是保持独立

- Phase 2/3/4 独立运行时，每个阶段都要手动准备输入数据、手动复制粘贴输出结果到下一阶段。四阶段串下来至少要 15 次手动操作。
- 总装后一键启动，中间只需要两次人机决策（视觉审核 + 特效审批），其余全自动。
- 老板看 Demo 时不可能等你手动跑四个脚本——一键出结果才是产品体验。

### 如果不做会怎样

四个模块代码都在但彼此孤立，Demo 时需要工程师手动衔接每一步。产品演示变成技术调试现场，老板看到的不是「AI 自动化生产工具」而是「命令行脚本集合」。商业 Demo 直接失败。

---

## 2026-05-20：修复 LangChain 1.x 导入报错

### 问题

运行 `streamlit run app.py` 时报错：`ModuleNotFoundError: No module named 'langchain.prompts'`。

### 为什么会出现这个报错

不是缺依赖包，是 LangChain 从 0.x 升级到 1.x 后，内部重新整理了模块结构。`ChatPromptTemplate` 这类底层组件被从 `langchain` 包移到了更底层的 `langchain_core` 包里。这就像公司重组——以前你找设计部在 3 楼，重组后搬到了 5 楼，你还去 3 楼敲门，当然没人应。

### 修复了什么

把 [app.py](app.py) 第 19 行的：
```python
from langchain.prompts import ChatPromptTemplate
```
改为：
```python
from langchain_core.prompts import ChatPromptTemplate
```

### 如果不修会怎样

应用完全无法启动。`import` 语句在 Python 里是程序启动时最先执行的东西，一个 import 失败整个程序直接炸，用户连界面都看不到。

### 怎么避免以后又出这种问题

可以在项目里加一个 `requirements.txt`，锁定所有依赖的精确版本号。这样下次在新机器上装环境时，装到的就是同样的版本，不会出现"你装的版本跟我开发时不一样"导致的路径变动问题。

---

## 2026-05-20：修复 LangChain 大括号转义冲突 Bug

### 问题

运行主程序时触发 `KeyError: Input to ChatPromptTemplate is missing variables... Expected: hook_sentences`。

### 根本原因

`system_prompt.txt` 里有一段 JSON 示例：
```json
{
  "hook_sentences": ["..."],
  "visual_constraints": ["..."],
  "product_pitch": ["..."]
}
```

用 `("system", system_prompt)` 这个元组写法传给 `ChatPromptTemplate.from_messages()` 时，LangChain 会把系统提示词也当成**模板**来处理。模板里的 `{hook_sentences}`、`{visual_constraints}`、`{product_pitch}` 全被当成变量占位符去找值——但根本没有这些变量，直接炸。

这就像你把一封带 `{{姓名}}` 模板标记的邮件交给打印机，打印机把邮件正文里 JSON 里的 `{` 也当成 `{{姓名}}` 了，然后告诉你"你少填了一个字段"。

### 解决方案

把系统提示词的传入方式从元组 `("system", text)` 改为 `SystemMessage(content=text)`。

**之前（有 Bug）**：
```python
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),    # ← 这里会被模板解析，JSON 的 {} 被误吞
    ("human", HUMAN_TEMPLATE),
])
```

**之后（已修复）**：
```python
prompt = ChatPromptTemplate.from_messages([
    SystemMessage(content=system_prompt),              # ← 原样传入，不解析
    HumanMessagePromptTemplate.from_template(HUMAN_TEMPLATE),  # ← 只有这里解析 {变量}
])
```

核心区别：
- `("system", text)` → LangChain 内部会对其做 `format()` → 花括号冲突
- `SystemMessage(content=text)` → 原封不动当字符串用 → 不冲突
- `HumanMessagePromptTemplate.from_template()` → 只对人类消息做变量替换 → `{target_ip_style}` 和 `{script}` 正常工作

### 为什么选这个方案而不是其他方案

| 方案 | 问题 |
|------|------|
| 把 txt 里 `{` 全改成 `{{` | system_prompt.txt 是人读的，塞双括号后运营看不懂，改提示词容易出错 |
| 用正则替换 | 治标不治本，哪天 JSON 里多了个新字段又得改 |
| `SystemMessage` 方案 ✅ | 代码层面一劳永逸，txt 文件保持干净可读 |

### 如果不修会怎样

程序完全不可用。任何包含 JSON 示例（有花括号）的系统提示词都会触发 KeyError，用户点击"开始精炼"后直接看到错误页面。

---

## 2026-05-20：代码资产封存 — 第一阶段功能测试通过

### 做了什么

将第一阶段所有核心资产通过 Git 提交并推送到 GitHub：
- `app.py` — Streamlit + LangChain 主程序（含正则预处理、提示词物理隔离加载、SystemMessage 花括号冲突修复、动态规则校验兜底）
- `system_prompt.txt` — 系统提示词物理隔离文件
- `MVP_PRD.md` — 产品架构文档
- `DEV_LOG.md` — 开发日记（本文档）
- `CLAUDE.md` — 项目规则
- `.claude/settings.json` — flake8 自动代码检查 Hook
- `.gitignore` — 忽略规则

### 为什么现在封存

第一阶段功能测试全部通过，代码处于稳定可运行状态。此时封存代码资产有两个目的：
1. 给后续开发一个干净的"回滚点"——万一第二阶段把代码改崩了，能一键回到现在这个稳定版本。
2. 上传到 GitHub 后代码不再只依赖本地硬盘，硬盘坏了也不怕。

### 如果不做会怎样

代码只存在于你本地机器上。硬盘故障、误删文件夹、换电脑——任何情况都可能导致全部工作丢失，重头再来。

---

## 2026-05-20：第二阶段架构设计 — 异步并发处理引擎

### 做了什么

新建了三个文件，完全独立于第一阶段的 `app.py`：

| 文件 | 职责 |
|------|------|
| `phase2_processor.py` | 异步并发处理主模块，接收 Phase 1 JSON，并行跑翻译 + 分镜两个通道 |
| `prompt_translation.txt` | 翻译通道的系统提示词（物理隔离） |
| `prompt_storyboard.txt` | 分镜通道的系统提示词（物理隔离） |

### 为什么用 asyncio 而不是多线程

翻译通道和分镜通道都是**网络 I/O 密集型任务**——99% 的时间在等 DeepSeek API 返回结果，不是在算东西。

- `asyncio`：一个线程管理多个等待中的网络请求。发出请求 A 后立刻发出请求 B，两个一起等结果。**CPU 几乎空闲，内存开销极低**。
- `ThreadPoolExecutor`（多线程）：每个任务开一个线程，线程切换有开销。适合 CPU 密集型任务（图像处理、数学计算），对纯网络等待是杀鸡用牛刀。

实际效果：
- 串行执行 = 翻译 3 秒 + 分镜 3 秒 = **6 秒**
- `asyncio.gather` 并行 = max(3 秒, 3 秒) = **~3 秒**
- **节省 50% 等待时间**

### 为什么不解耦会带来性能灾难

如果第二阶段代码塞进 `app.py`：
1. **UI 阻塞**：Streamlit 是单线程同步框架。`app.py` 里如果做 6 秒串行 AI 调用，用户界面直接卡住 6 秒，什么都点不了。
2. **改提示词要重启**：翻译和分镜的提示词如果硬编码在 `app.py` 里，改一个字整个 Streamlit 应用重启，终端用户掉线。
3. **无法独立监控**：以后你想看"翻译通道平均耗时多少"、"分镜通道 GPU 利用率多少"，两个通道搅在一起根本拆不开。
4. **无法独立扩容**：以后翻译想用便宜模型、分镜想用好模型？代码耦合的情况下根本做不到。

### 架构设计的关键决策

**1. `asyncio.gather` + `return_exceptions=True`**

一个通道炸了不会拖垮另一个。翻译通了但分镜挂了，翻译结果照样返回，分镜那边返回错误信息。
这保证了"尽力而为"——而不是"一个挂全挂"。

**2. 提示词物理隔离**

和第一阶段一样，翻译和分镜的系统提示词全放在 `.txt` 文件里。产品/运营可以直接改分镜的艺术风格、翻译的语气偏好，不需要碰代码。

**3. SystemMessage 防花括号冲突**

吸取第一阶段的教训，翻译和分镜的提示词全部用 `SystemMessage(content=...)` 传入，避免 txt 里 JSON 示例的花括号被 LangChain 误当变量。

**4. Temperature = 0.3（非 0.1）**

第二阶段任务（翻译自然度、分镜创意）需要比第一阶段（结构化抽取）稍高的灵活性。0.3 是"稳定但不僵硬"的折中值。

**5. 同步包装器 `process_phase2_sync()`**

因为 Streamlit 不能直接 `await` 异步函数，所以提供了一个 `asyncio.run()` 包装器。未来如果换成 FastAPI（原生支持 async），直接把包装器扔掉，用 `await process_phase2()` 即可。

### 数据流

```
app.py (Phase 1) 输出 JSON
         │
         │  { hook_sentences, visual_constraints,
         │    product_pitch, script, target_ip_style }
         ▼
process_phase2(phase1_json, target_language="en")
         │
         │  asyncio.gather ─────┐
         │                      │
    ┌────▼─────┐         ┌─────▼─────┐
    │ 翻译通道  │         │ 分镜通道   │
    │ ainvoke  │         │ ainvoke   │
    └────┬─────┘         └─────┬─────┘
         │                      │
         └──────────┬───────────┘
                    ▼
       { translation: {...},
         storyboard: {...} }
```

### 如果不做会怎样

第二阶段功能根本不存在。用户拿了第一阶段的结构化 JSON 后，还得手动把带货金句丢进 Google 翻译、把 Hook 句子丢进 Midjourney 写 Prompt。一次 3 秒能解决的事，变成 30 分钟的人工操作。

---

## 2026-05-21：第四阶段完工 — 半自动装配车间

新建 `phase4_assembly.py`，实现三大模块：

1. **时间轴对齐引擎** — `build_timeline()`，以 TTS 音频为锚点，毫秒级对齐音频/视觉/字幕三条轨道，输出结构化 Timeline JSON。
2. **智能特效方案** — `generate_effects_plan()`，基于剧本关键词做情绪检测，自动推荐 BGM、转场方案、关键帧缩放策略、调色预设、叠加特效。
3. **人机协作最终防线** — `human_final_approval()`，打印特效方案后 `input()` 阻塞等待人类输入"确认/修改/驳回"，只有确认通过才输出最终装配成功日志。

---

## 2026-05-21：第三阶段完工 — 多模态视觉铸造与品控车间

新建 `phase3_multimodal.py`，实现三大模块：

1. **TTS 配音通道** — `text_to_speech()` / `batch_tts()`，预留真实语音 API 接口，当前 Mock 模式生成占位音频文件。
2. **黄金 30 秒视觉路由** — `visual_distribution_router()`，前 30s 强制路由到视频生成 API，30s 后强制路由到图像生成 API，以最小成本最大化留存率。
3. **人机品控拦截器** — `human_review_interceptor()`，视觉素材输出后阻塞等待人工输入"确认采纳"，支持逐条审核和批量审核两种模式。

---

## 2026-05-20：项目初始化 & MVP 第一阶段搭建

### 1. 选了 Streamlit 做界面，而不是 HTML/JS

**做了什么**：用 `streamlit` 库搭了一个纯 Python 的网页界面，包含文本框、下拉菜单、按钮。

**为什么这么做**：
- 你没前端基础，我也不想写 HTML/CSS/JS。Streamlit 只用 Python 就能出网页，3 行代码一个按钮，5 行代码一个文本框。
- 对 MVP 来说，界面只要能用就行，不需要好看。Streamlit 自带样式，开箱即用。
- 以后你想换 Vue/React 重做前端，后端逻辑完全不用动——因为 Streamlit 只是薄薄一层皮。

**如果不这么做**：你自己得学 HTML + CSS + JS，或者花钱找个前端兼职。出 MVP 的速度至少慢一周。

---

### 2. 选了 LangChain 做编排层，而不是直接调 DeepSeek API

**做了什么**：用 `langchain_openai.ChatOpenAI` 包了一层 DeepSeek API。

**为什么这么做**：
- 直接调 API 就是 `requests.post()`，功能是能实现，但提示词管理、链式调用、错误重试全都得手写。
- LangChain 的 `ChatPromptTemplate` 把系统提示词和用户消息分开管理，结构清晰。以后你想加「多轮对话」「Few-shot 示例」「RAG 检索」，直接在 LangChain 框架里加，不用推倒重来。
- DeepSeek 的 API 跟 OpenAI 兼容，所以用 `ChatOpenAI` 类就能直接连上，不需要额外封装。

**如果不这么做**：你也能跑通，但代码会变成一坨意大利面条——`requests` 里混着满屏的 f-string 拼提示词，三个月后没人敢改。

---

### 3. 正则预处理放在 Python 侧，而不是让大模型自己清理

**做了什么**：在 `preprocess_script()` 函数里用 Python 的 `re` 模块清理不可见字符和多余空行。

**为什么这么做**：
- 大模型不是免费的——DeepSeek API 按 token 计费。多余的空行、零宽空格这些垃圾字符如果原样送进去，白白浪费 token 钱。
- 大模型不会"清理文本"，它只会"生成文本"。你把脏数据丢进去，它可能把垃圾字符当正经内容理解，输出也跟着跑偏。
- 正则处理是本地的，1 毫秒完成，零成本。

**如果不这么做**：每次调用多花 ~10% 的 token 费用，而且输出质量不稳定（有时候模型会被垃圾字符带偏）。

---

### 4. Temperature 设为 0.1，不是 0.7，也不是 0

**做了什么**：把大模型的 `temperature` 参数设为 `0.1`。

**为什么这么做**：
- Temperature 控制模型的"想象力"，范围 0~2。越高越天马行空，越低越死板但稳定。
- 脚本精炼是**结构化抽取**任务——你需要的是准、稳，不是创意。0.1 给了模型一点点灵活性（避免逐字照抄），但不会瞎编。
- 如果设成 0——模型每次输出一模一样，但可能卡壳（某些 API 在 0 时会出奇怪问题）。0.1 是最安全的"几乎不变"的值。
- 如果设成 0.7——模型会开始自由发挥，hook_sentences 里可能蹦出剧本里根本没有的句子。

**如果不这么做**：带货金句变"诗歌创作"，视觉约束变"科幻小说场景"，下游视频生成全乱套。

---

### 5. 强制开启 JSON Mode，不用自然语言拼 JSON

**做了什么**：在 ChatOpenAI 的 `model_kwargs` 里设置了 `"response_format": {"type": "json_object"}`。

**为什么这么做**：
- 大模型本质是"文字接龙"，如果不强制 JSON Mode，它可能在 JSON 前面加一句"好的，以下是分析结果："，或者在 JSON 后面加一段"希望对你有帮助！"。
- 这些废话在 JSON 解析时会直接报错崩溃。强制 JSON Mode 后，模型被限制只能输出 JSON，不会有多余文字。
- 代码里还做了一层兜底：如果 JSON 解析失败，用正则从输出里把 `{...}` 扣出来再试一次。两层保险。

**如果不这么做**：大概 30% 的调用会 JSON 解析失败，用户看到一个错误页面，体验稀烂。

---

### 6. 系统提示词从代码里拆出去，放到独立 txt 文件

**做了什么**：创建了 `system_prompt.txt`，app.py 运行时从文件加载，而不是硬编码在 Python 代码里。

**为什么这么做**：
- 你是产品经理，你应该有权随时调优 AI 的行为，而不是每次改一个词都要找程序员改代码。
- 物理隔离后，你可以直接打开 txt 文件编辑提示词，下次调用自动生效，不需要重启。
- 以后你可以把不同场景的提示词做成不同版本（system_prompt_v2.txt、system_prompt_带货版.txt），A/B 测试很方便。
- 即使 txt 文件不小心被删了，代码里有兜底的默认提示词，不会崩。

**如果不这么做**：改一个提示词你得找我来改代码 → 测试 → 部署，一个词迭代要 20 分钟。

---

### 7. 动态规则校验兜底——不会漏掉用户选的视觉基调

**做了什么**：`enforce_visual_constraints()` 函数扫描大模型输出的 `visual_constraints`，如果没包含用户选的 `Target_IP_Style`，强行追加进去。

**为什么这么做**：
- 大模型不是 100% 可靠的——有时候用户选了"3D拟人化水果角色"，但模型输出的视觉约束只提了"室内场景""明亮灯光"，完全没提"水果角色"。
- 下游的视频生成模块如果收到一个缺了"水果角色"的画面描述，产出的就是完全不对路的视频。
- 这个校验是代码层的最后一道安全网，不管你模型出什么结果，我都能保证视觉基调不会丢。

**如果不这么做**：用户选了"美国街头风"生成视频，结果出来的画面是一个中国办公室。用户直接关掉你的 App 再也不回来。这种 Bug 靠人工 QA 测不过来，必须代码自动兜底。

---

### 8. 配置了 flake8 自动代码检查 Hook

**做了什么**：在 `.claude/settings.json` 里配了一个 PostToolUse Hook，每次我写或改 Python 文件后自动跑 flake8，违规立刻反馈。

**为什么这么做**：
- AI 写的代码也可能有规范问题（行太长、变量未使用、缩进错误等）。人工 Code Review 对你不现实（你是产品经理），所以让机器自动查。
- flake8 是 Python 社区最常用的代码规范检查工具，速度快（毫秒级），规则清晰。
- Hook 是事后检查（PostToolUse），不会阻止我写代码，只会发现问题后反馈给我让我立刻修。

**如果不这么做**：代码质量全靠我自觉，不规范日积月累，三个月后改一行代码引出一堆 bug。

---

### 9. Git 推送走代理

**做了什么**：配置了 `git config http.proxy http://127.0.0.1:7890`，让 git 走本地代理连 GitHub。

**为什么这么做**：
- 你在中国大陆，直连 GitHub 会被墙，每次 push/pull 都超时。
- 你的代理软件在本地 7890 端口运行，配好后 git 自动走代理，不用每次手动翻墙。

**如果不这么做**：代码永远推不上 GitHub，只能躺在你本地硬盘里。硬盘一坏就全没了。

---

## 开发日记使用约定

- 每次新建或大规模修改核心文件（app.py、system_prompt.txt、架构调整等），我会在本文最上面追加新条目。
- 格式固定：**日期 + 做了什么 + 为什么 + 不做的后果**。
- 技术术语会附带大白话解释，确保非技术读者能看懂。
