"""
================================================================================
 启量 Agent — 短视频自动化生产工具 MVP（第一阶段：脚本精炼引擎）
 技术栈：Streamlit（前端） + LangChain（编排） + DeepSeek API（大模型）
================================================================================

 【API Key 填写指引】
 将下方 YOUR_DEEPSEEK_API_KEY 替换为你的 DeepSeek API Key。
 获取地址：https://platform.deepseek.com/api_keys
 注意：请勿将 API Key 提交到公开仓库，生产环境请用环境变量管理。
================================================================================
"""

import re
import json
import os
import streamlit as st
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage

# ============================================================================
# 全局配置区
# ============================================================================

# ── 请将下方的字符串替换为你自己的 DeepSeek API Key ──
YOUR_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# DeepSeek API 的兼容端点（OpenAI 兼容协议）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 模型名称：deepseek-chat 即 DeepSeek-V3，适合结构化输出任务
MODEL_NAME = "deepseek-chat"

# 大模型温度参数：0.1 确保输出稳定、可复现，减少随机性
TEMPERATURE = 0.1


# ============================================================================
# 模块一：输入预处理层
# ============================================================================

def preprocess_script(raw_text: str) -> str:
    """
    用纯 Python 正则表达式清理用户输入的短视频剧本。
    清理目标：
      1. 剔除不可见字符（例如零宽空格、控制字符等）
      2. 将连续 3 个以上的空行压缩为最多 2 个空行，保留合理段落间距
      3. 去除首尾多余的空白
    """
    # 步骤 1：删除所有不可见的控制字符（\x00-\x1F 和 \x7F-\x9F），
    #         但保留换行符 \n（\x0A）和回车符 \r（\x0D），因为它们是合法的段落分隔符。
    #         这个正则匹配除了 \n \r 之外的所有控制字符。
    cleaned = re.sub(r"[\x00-\x09\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", raw_text)

    # 步骤 2：将 3 个及以上的连续空行压缩为恰好 2 个空行（即 3 个连续的 \n）。
    #         (?:\n\s*){3,} 表示 3 组以上的"换行 + 可选空格"。
    cleaned = re.sub(r"(?:\n\s*){3,}", "\n\n", cleaned)

    # 步骤 3：去除整个文本首尾多余的空白字符
    cleaned = cleaned.strip()

    return cleaned


# ============================================================================
# 模块二 & 三：LangChain 调度与强约束 JSON 输出
# ============================================================================

# 定义大模型输出的 JSON 结构 —— 用 Prompt 强约束，同时配合 DeepSeek 的 JSON Mode
# 三个字段的含义：
#   hook_sentences     — 吸引眼球的故事引子和冲突句（字符串列表）
#   visual_constraints — 服装、环境等硬性画面要求（字符串列表）
#   product_pitch      — 带货金句（字符串列表）


def load_system_prompt() -> str:
    """
    从外部文件 system_prompt.txt 加载系统提示词。
    实现提示词的物理隔离，产品和运营可以直接编辑 txt 文件来调优 AI 行为，
    无需修改 Python 代码，无需重启服务（下次调用时自动生效）。

    如果文件不存在，退回内置的默认提示词作为兜底。
    """
    # system_prompt.txt 与 app.py 放在同一个目录下
    prompt_file = os.path.join(os.path.dirname(__file__), "system_prompt.txt")

    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()

    # ── 兜底提示词：当 system_prompt.txt 丢失时使用 ──
    return """\
你是一个顶级的短视频脚本精炼专家。你的任务是将用户输入的剧本拆解为三个维度，并以严格的 JSON 格式输出。

【输出要求】
1. 必须只输出一个合法的 JSON 对象，不要在 JSON 前后附加任何解释、说明或 Markdown 代码块标记。
2. JSON 必须包含以下三个字段，且每个字段的值都是一个字符串数组（string[]）：

  - "hook_sentences"：从剧本中提取出最能吸引观众注意力的故事引子和冲突句。
      这些句子要能让用户在 3 秒内产生好奇心，不愿意划走。
  - "visual_constraints"：从剧本中分析出的服装、场景、道具、天气、
      时间等硬性画面拍摄要求。每条要求用一句自然语言描述。
  - "product_pitch"：剧本中的带货金句、产品卖点、促销话术。
      如果没有明显的带货语句，请返回空数组 []。

3. 每条内容必须简洁有力，不超过 30 个字。
4. 如果剧本中某类信息缺失，对应字段返回空数组 []，严禁编造。

【输出示例】
{{
  "hook_sentences": ["悬念引子示例1", "冲突句示例2"],
  "visual_constraints": ["场景要求示例1", "服装要求示例2"],
  "product_pitch": ["带货金句示例1"]
}}
"""


# 人类消息模板 —— 把用户选定的视觉基调和剧本内容一起送进模型
HUMAN_TEMPLATE = """\
【目标视觉基调】：{target_ip_style}
【短视频剧本内容】：
{script}

请按照系统提示中的 JSON 格式输出精炼结果。"""


def build_chain(api_key: str = YOUR_API_KEY):
    """
    构建并返回一个 LangChain 处理链。
    链的结构：Prompt 模板 → 大模型（DeepSeek，JSON Mode 开启）

    系统提示词从 system_prompt.txt 文件动态加载，支持热更新。

    参数：
      api_key — DeepSeek API Key，可从 Streamlit 界面动态传入，
                未传入时使用代码顶部的默认值。
    """
    # 初始化 DeepSeek 大模型（通过 OpenAI 兼容协议）
    llm = ChatOpenAI(
        api_key=api_key,                         # API Key（支持动态传入）
        base_url=DEEPSEEK_BASE_URL,              # DeepSeek 端点
        model=MODEL_NAME,                        # 模型
        temperature=TEMPERATURE,                 # 低温度 → 稳定输出
        model_kwargs={
            "response_format": {"type": "json_object"}  # 强制 JSON Mode
        },
    )

    # 从 system_prompt.txt 动态加载系统提示词（物理隔离，支持热更新）
    system_prompt = load_system_prompt()

    # 用 SystemMessage 传入系统提示词——不经过模板格式化，
    # 避免 txt 里 JSON 示例的 { } 被 LangChain 误当成变量占位符。
    # 人类消息用 HumanMessagePromptTemplate，保留 {target_ip_style} 和 {script} 变量替换。
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessagePromptTemplate.from_template(HUMAN_TEMPLATE),
    ])

    # 用 LCEL（LangChain Expression Language）把 prompt 和 llm 串成链
    chain = prompt | llm

    return chain


def invoke_chain(chain, script: str, target_ip_style: str) -> dict:
    """
    调用 LangChain 链，输入预处理后的剧本和目标视觉基调，返回解析后的字典。
    如果模型返回的不是合法 JSON，做一次容错兜底。
    """
    # 调用链，获取大模型返回的原始消息
    response = chain.invoke({
        "script": script,
        "target_ip_style": target_ip_style,
    })

    # response.content 是模型生成的文本（应该是一段 JSON 字符串）
    raw_output = response.content.strip()

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        # 如果 JSON 解析失败，尝试用正则从原始输出中提取 JSON 对象
        # 这是兜底策略：有些模型可能在 JSON 前后加了少量文字
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                # 两次解析都失败，返回一个结构一致的空结果
                result = {
                    "hook_sentences": [],
                    "visual_constraints": [],
                    "product_pitch": [],
                }
        else:
            result = {
                "hook_sentences": [],
                "visual_constraints": [],
                "product_pitch": [],
            }

    # 确保三个字段都存在，缺的补空数组
    for key in ["hook_sentences", "visual_constraints", "product_pitch"]:
        if key not in result:
            result[key] = []

    return result


# ============================================================================
# 模块四：动态规则校验兜底
# ============================================================================

def enforce_visual_constraints(result: dict, target_ip_style: str) -> dict:
    """
    扫描 visual_constraints 字段。
    如果其中没有包含用户选定的 Target_IP_Style 关键词，
    则强行将其追加（Append）到视觉约束列表中。

    这样确保最终的画面要求不会遗漏用户指定的整体视觉基调。
    """
    constraints = result.get("visual_constraints", [])

    # 把 target_ip_style 中的关键字符提取出来做模糊匹配
    # 例如用户选 "3D拟人化水果角色" → 检查 "水果" 是否出现在现有约束中
    # 也同时做整体字符串包含检查
    style_included = False

    for constraint in constraints:
        # 检查约束文本中是否已提到目标风格的关键片段
        if target_ip_style in constraint:
            style_included = True
            break
        # 做一次反向检查：目标风格是否包含约束中的关键词
        # 这是为了处理用户可能在约束中用简称的情况
        if constraint and len(constraint) >= 2 and constraint in target_ip_style:
            style_included = True
            break

    # 如果所有约束都没有匹配到目标风格，强行追加
    if not style_included:
        constraints.append(f"整体视觉基调：{target_ip_style}")
        result["visual_constraints"] = constraints

    return result


# ============================================================================
# Streamlit 可视化界面
# ============================================================================

def main():
    """
    Streamlit 应用入口 —— 搭建极简的可视化网页界面。
    布局从上到下：
      1. 标题与说明
      2. 侧边栏：API Key 配置 + 视觉基调选择
      3. 主区域：剧本输入文本框
      4. 按钮：触发处理流水线
      5. 结果展示区
    """

    # ── 页面基础配置 ──
    st.set_page_config(
        page_title="启量 Agent · 脚本精炼引擎",
        page_icon="🎬",
        layout="wide",
    )

    st.title("🎬 启量 Agent — 脚本精炼引擎（MVP 第一阶段）")
    st.markdown("输入你的短视频剧本，AI 自动拆解为 **引子句 · 画面要求 · 带货金句**。")

    # ── 侧边栏：可调参数 ──
    with st.sidebar:
        st.header("⚙️ 参数配置")

        # 动态参数选择 —— 视觉基调下拉菜单
        target_ip_style = st.selectbox(
            label="🎨 Target IP Style（视觉基调）",
            options=[
                "3D拟人化水果角色",
                "美国真实街头风",
            ],
            index=0,  # 默认选中第一项
            help="选择视频的整体视觉风格基调，将影响 AI 对画面要求的提取。",
        )

        st.divider()

        # API Key 输入框 —— 允许用户在网页上直接填入，覆盖代码中的默认值
        user_api_key = st.text_input(
            label="🔑 DeepSeek API Key",
            type="password",
            value=YOUR_API_KEY if YOUR_API_KEY != "sk-d14103b94fd94a798f9d7dab627e1de0" else "",
            placeholder="在此粘贴你的 DeepSeek API Key",
            help="从 https://platform.deepseek.com/api_keys 获取。不会存储到服务器。",
        )

        st.divider()
        st.caption("📦 技术栈：Streamlit + LangChain + DeepSeek")
        st.caption("🌡 Temperature = 0.1  |  JSON Mode = ON")

    # ── 主区域：剧本输入 ──
    st.subheader("📝 短视频剧本")
    raw_script = st.text_area(
        label="请在此粘贴或输入你的短视频剧本",
        height=240,
        placeholder="例如：\n\n你有没有想过，为什么超市里的苹果永远那么亮？\n其实背后藏着一个不为人知的秘密...\n\n今天我们就来揭秘水果保鲜的黑科技！\n这款保鲜喷雾，喷一下就能让水果发光7天...",
        help="支持多行文本，AI 会自动清理多余空行和不可见字符。",
    )

    # ── 运行按钮 ──
    col1, col2, col3 = st.columns([1, 1, 6])
    with col1:
        run_button = st.button(
            "🚀 开始精炼",
            type="primary",
            disabled=False,
            use_container_width=True,
        )
    with col2:
        clear_button = st.button(
            "🗑 清空结果",
            use_container_width=True,
        )

    if clear_button:
        # 清空历史结果（通过操作 session_state）
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    # ── 结果显示区域 ──
    st.divider()
    st.subheader("📊 精炼结果")

    # 用占位符来动态更新结果区域
    result_placeholder = st.empty()

    if run_button:
        # ── 输入验证 ──
        if not raw_script or not raw_script.strip():
            st.error("❌ 请先输入剧本内容再点击精炼。")
            return

        final_api_key = user_api_key.strip() if user_api_key.strip() else YOUR_API_KEY
        if not final_api_key or final_api_key == "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
            st.error("❌ 请先在侧边栏填入有效的 DeepSeek API Key。")
            return

        # ── 流水线执行步骤（用进度条给用户可见的反馈）──
        with st.spinner("🔄 流水线运行中，请稍候..."):
            progress_bar = st.progress(0, text="正在预处理剧本...")

            # 步骤 1：预处理
            cleaned_script = preprocess_script(raw_script)
            progress_bar.progress(20, text="预处理完成，正在调用 AI 模型...")

            # 步骤 2：构建链（动态注入用户填写的 API Key）
            chain = build_chain(api_key=final_api_key)

            progress_bar.progress(40, text="AI 模型推理中（约 3~5 秒）...")

            # 步骤 3：调用链
            result = invoke_chain(chain, cleaned_script, target_ip_style)
            progress_bar.progress(70, text="正在执行规则校验...")

            # 步骤 4：动态规则校验兜底
            result = enforce_visual_constraints(result, target_ip_style)
            progress_bar.progress(90, text="校验完成，正在渲染结果...")

            progress_bar.progress(100, text="✅ 完成！")
            st.toast("精炼完成！", icon="✅")

        # ── 结果渲染 ──
        with result_placeholder.container():
            st.success("### ✅ 精炼成功！")

            # 三列布局展示三个维度的结果
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                st.markdown("#### 🔥 引子 / 冲突句")
                hooks = result.get("hook_sentences", [])
                if hooks:
                    for idx, sentence in enumerate(hooks, start=1):
                        # 用高亮样式展示每一条
                        st.markdown(f"> **{idx}.** {sentence}")
                else:
                    st.caption("（未提取到相关内容）")

            with col_b:
                st.markdown("#### 🎬 画面约束")
                visuals = result.get("visual_constraints", [])
                if visuals:
                    for idx, constraint in enumerate(visuals, start=1):
                        # 如果约束是刚刚被代码追加的，加一个标记
                        if ("整体视觉基调" in constraint
                                and target_ip_style in constraint):
                            st.markdown(f"> **{idx}.** {constraint} 🛡️")
                        else:
                            st.markdown(f"> **{idx}.** {constraint}")
                else:
                    st.caption("（未提取到相关内容）")

            with col_c:
                st.markdown("#### 💰 带货金句")
                pitches = result.get("product_pitch", [])
                if pitches:
                    for idx, pitch in enumerate(pitches, start=1):
                        st.markdown(f"> **{idx}.** {pitch}")
                else:
                    st.caption("（未提取到相关内容）")

            # 折叠区：原始 JSON（方便你调试 / 对接下游系统）
            with st.expander("🔍 查看完整 JSON 输出", expanded=False):
                st.json(result)

            # 折叠区：对比预处理前后的文本
            with st.expander("📋 查看预处理前后对比", expanded=False):
                comp_col_a, comp_col_b = st.columns(2)
                with comp_col_a:
                    st.caption("原始输入")
                    st.text(raw_script)
                with comp_col_b:
                    st.caption("预处理后（传给 AI 的文本）")
                    st.text(cleaned_script)


# ============================================================================
# 程序入口
# ============================================================================

if __name__ == "__main__":
    main()
