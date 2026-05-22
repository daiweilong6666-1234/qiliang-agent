"""
================================================================================
 启量 Agent — 短视频自动化生产工具 MVP（全线总装版）
 技术栈：Streamlit（前端） + LangChain（编排） + DeepSeek API（大模型）
 四阶段流水线：脚本精炼 → 翻译+分镜并发 → 多模态路由品控 → 时间轴装配
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

# 引入 phase2 / phase3 / phase4 的核心入口函数
from phase2_processor import process_phase2_sync
from phase3_multimodal import (
    batch_tts, visual_distribution_router,
)
from phase4_assembly import (
    build_timeline, generate_effects_plan,
)

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
    cleaned = re.sub(r"[\x00-\x09\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", raw_text)
    cleaned = re.sub(r"(?:\n\s*){3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned


# ============================================================================
# 模块二 & 三：LangChain 调度与强约束 JSON 输出
# ============================================================================


def load_system_prompt() -> str:
    """
    从外部文件 system_prompt.txt 加载系统提示词。
    实现提示词的物理隔离，产品和运营可以直接编辑 txt 文件来调优 AI 行为，
    无需修改 Python 代码，无需重启服务（下次调用时自动生效）。

    如果文件不存在，退回内置的默认提示词作为兜底。
    """
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
    """
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        model_kwargs={
            "response_format": {"type": "json_object"}
        },
    )

    system_prompt = load_system_prompt()

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessagePromptTemplate.from_template(HUMAN_TEMPLATE),
    ])

    chain = prompt | llm
    return chain


def invoke_chain(chain, script: str, target_ip_style: str) -> dict:
    """
    调用 LangChain 链，输入预处理后的剧本和目标视觉基调，返回解析后的字典。
    如果模型返回的不是合法 JSON，做一次容错兜底。
    """
    response = chain.invoke({
        "script": script,
        "target_ip_style": target_ip_style,
    })

    raw_output = response.content.strip()

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
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
    """
    constraints = result.get("visual_constraints", [])

    style_included = False

    for constraint in constraints:
        if target_ip_style in constraint:
            style_included = True
            break
        if constraint and len(constraint) >= 2 and constraint in target_ip_style:
            style_included = True
            break

    if not style_included:
        constraints.append(f"整体视觉基调：{target_ip_style}")
        result["visual_constraints"] = constraints

    return result


# ============================================================================
# 流水线状态管理
# ============================================================================

def init_session_state():
    """初始化所有 session_state 变量。"""
    defaults = {
        "pipeline_stage": "idle",
        "phase1_result": None,
        "phase2_result": None,
        "phase3_result": None,
        "phase4_result": None,
        "cleaned_script": None,
        "reviewed_visuals": None,
        "approval_decision": None,
        "pipeline_error": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ============================================================================
# 各阶段执行函数
# ============================================================================

def execute_phase1(cleaned_script: str, target_ip_style: str, api_key: str) -> dict:
    """执行 Phase 1：脚本精炼。"""
    chain = build_chain(api_key=api_key)
    result = invoke_chain(chain, cleaned_script, target_ip_style)
    result = enforce_visual_constraints(result, target_ip_style)
    return result


def execute_phase2(phase1_result: dict, cleaned_script: str,
                   target_ip_style: str, api_key: str) -> dict:
    """执行 Phase 2：翻译 + 分镜异步并发。"""
    phase1_json = {
        **phase1_result,
        "script": cleaned_script,
        "target_ip_style": target_ip_style,
    }
    return process_phase2_sync(phase1_json, api_key=api_key)


def execute_phase3_routing(phase2_result: dict) -> dict:
    """执行 Phase 3：TTS 配音 + 视觉分发路由。"""
    storyboard = phase2_result.get("storyboard", {})
    storyboard_prompts = storyboard.get("storyboard_prompts", [])
    translation = phase2_result.get("translation", {})

    # TTS 文本片段：必须使用 Phase 2 翻译通道输出的高置信度英文文本，
    # 而非 Phase 1 的中文原句。按英文句子边界拆分 translated_script，
    # 再追加 translated_pitches。
    translated_script = translation.get("translated_script", "")
    translated_pitches = translation.get("translated_pitches", [])

    tts_segments = []
    if translated_script:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', translated_script) if s.strip()]
        tts_segments.extend(sentences)
    if translated_pitches:
        tts_segments.extend(translated_pitches)
    tts_results = []
    if tts_segments:
        tts_audio_list = batch_tts(tts_segments)
        for idx, (seg, audio) in enumerate(zip(tts_segments, tts_audio_list)):
            tts_results.append({
                "text": seg,
                "audio_path": audio.get("audio_path", ""),
                "duration_seconds": audio.get("duration_seconds", 2.0),
                "voice_id": audio.get("voice_id", "default"),
                "segment_index": idx + 1,
            })

    # 将 storyboard_prompts（字符串列表）转换为视觉路由所需格式
    shots_for_routing = []
    cumulative_time = 0
    for i, prompt_text in enumerate(storyboard_prompts):
        # 每个分镜预估 5~8 秒
        shot_duration = min(8.0, max(4.0, len(prompt_text) * 0.03))
        cumulative_time += shot_duration
        shots_for_routing.append({
            "prompt": prompt_text,
            "duration_seconds": round(cumulative_time, 1),
        })

    visual_results = []
    if shots_for_routing:
        visual_results = visual_distribution_router(shots_for_routing)

    return {
        "tts": tts_results,
        "visual": visual_results,
        "tts_segments": tts_segments,
    }


def execute_phase4_assembly(phase3_result: dict, cleaned_script: str) -> dict:
    """执行 Phase 4：时间轴对齐 + 智能特效方案。"""
    tts_segments = phase3_result.get("tts", [])
    visual_shots = st.session_state.get("reviewed_visuals", [])

    if not visual_shots:
        visual_shots = phase3_result.get("visual", [])

    return build_timeline_and_effects(tts_segments, visual_shots, cleaned_script)


def build_timeline_and_effects(tts_segments: list, visual_shots: list,
                               script_text: str) -> dict:
    """执行时间轴对齐和特效方案生成。"""
    timeline = build_timeline(
        tts_segments=tts_segments,
        visual_shots=visual_shots,
    )

    effects_plan = generate_effects_plan(
        script_text=script_text,
        total_duration_ms=timeline["total_duration_ms"],
        shot_count=len(timeline["tracks"]["video"]),
    )

    return {
        "timeline": timeline,
        "effects_plan": effects_plan,
    }


# 剪映草稿输出目录
OUTPUT_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "output_assets")


def _generate_jianying_draft(phase4_result: dict, phase1_result: dict,
                             phase2_result: dict) -> dict:
    """
    生成剪映底层草稿 JSON 文件。
    这是私有化部署的最终产物——下游剪辑师或自动化脚本可直接将此 JSON
    导入剪映桌面端 / 剪映 SaaS API，进入人工精修环节。
    """
    timeline = phase4_result.get("timeline", {})
    effects = phase4_result.get("effects_plan", {})
    approval = phase4_result.get("approval", {})

    draft = {
        "draft_name": "启量Agent_自动生成草稿",
        "version": "1.0.0",
        "platform": "qiliang_agent_private_deploy",
        "created_at": timeline.get("created_at", ""),
        "duration_ms": timeline.get("total_duration_ms", 0),
        "tracks": timeline.get("tracks", {}),
        "effects": {
            "bgm": effects.get("recommended_bgm", {}),
            "transitions": effects.get("transition_plan", []),
            "keyframe": effects.get("keyframe_plan", {}),
            "color_grading": effects.get("color_grading", ""),
            "overlays": effects.get("overlay_effects", []),
        },
        "human_approval": {
            "decision": approval.get("human_decision", "N/A"),
            "status": approval.get("final_status", "N/A"),
            "feedback": approval.get("human_feedback", ""),
            "timestamp": approval.get("timestamp", ""),
        },
        "source_script": {
            "hooks": phase1_result.get("hook_sentences", []),
            "pitches": phase1_result.get("product_pitch", []),
        },
    }

    # 保存草稿 JSON 到 output_assets
    os.makedirs(OUTPUT_ASSETS_DIR, exist_ok=True)
    draft_path = os.path.join(OUTPUT_ASSETS_DIR, "jianying_draft.json")
    with open(draft_path, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    draft["file_path"] = draft_path
    return draft


# ============================================================================
# Streamlit 可视化界面
# ============================================================================

def main():
    """
    Streamlit 应用入口 —— 四阶段流水线总装版。
    流水线：脚本精炼 → 翻译+分镜并发 → 多模态路由品控 → 时间轴装配
    人机协作节点：视觉素材审核（Phase 3 后）、特效方案审批（Phase 4 后）
    """

    st.set_page_config(
        page_title="启量 Agent · 全线总装",
        page_icon="🎬",
        layout="wide",
    )

    init_session_state()

    st.title("🎬 启量 Agent — 短视频自动化生产工具")
    st.markdown(
        "四阶段流水线：**脚本精炼** → **翻译+分镜并发** → "
        "**多模态路由品控** → **时间轴装配**"
    )

    # ── 侧边栏 ──
    with st.sidebar:
        st.header("⚙️ 参数配置")

        target_ip_style = st.selectbox(
            label="🎨 Target IP Style（视觉基调）",
            options=[
                "3D拟人化水果角色",
                "美国真实街头风",
            ],
            index=0,
            help="选择视频的整体视觉风格基调。",
        )

        st.divider()

        user_api_key = st.text_input(
            label="🔑 DeepSeek API Key",
            type="password",
            value=YOUR_API_KEY if YOUR_API_KEY != "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" else "",
            placeholder="在此粘贴你的 DeepSeek API Key",
            help="从 https://platform.deepseek.com/api_keys 获取。",
        )

        st.divider()

        # 流水线状态指示器
        stage = st.session_state.get("pipeline_stage", "idle")
        stage_labels = {
            "idle": "⏳ 等待启动",
            "awaiting_review": "👁 等待品控审核",
            "awaiting_approval": "✅ 等待特效审批",
            "video_review": "🎥 最终视频审核",
            "complete": "🏁 流水线完成",
        }
        st.markdown(f"**流水线状态**: {stage_labels.get(stage, stage)}")

        if stage != "idle":
            if st.button("🔄 重置流水线", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

    # ── 主区域：剧本输入 ──
    st.subheader("📝 短视频剧本")
    raw_script = st.text_area(
        label="请在此粘贴或输入你的短视频剧本",
        height=200,
        placeholder="例如：\n\n你有没有想过，为什么超市里的苹果永远那么亮？\n其实背后藏着一个不为人知的秘密...\n\n今天我们就来揭秘水果保鲜的黑科技！\n这款保鲜喷雾，喷一下就能让水果发光7天...",
        help="支持多行文本，AI 会自动清理多余空行和不可见字符。",
    )

    # ── 启动按钮 ──
    stage = st.session_state.get("pipeline_stage", "idle")

    if stage == "idle":
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 6])
        with col1:
            launch_btn = st.button(
                "🚀 启动全线流水线",
                type="primary",
                use_container_width=True,
            )

        if launch_btn:
            if not raw_script or not raw_script.strip():
                st.error("❌ 请先输入剧本内容再启动流水线。")
                return

            final_api_key = user_api_key.strip() if user_api_key.strip() else YOUR_API_KEY
            if not final_api_key or final_api_key == "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
                st.error("❌ 请先在侧边栏填入有效的 DeepSeek API Key。")
                return

            st.session_state["target_ip_style"] = target_ip_style
            st.session_state["api_key"] = final_api_key

            # ── 依次执行 Phase 1 → Phase 2 → Phase 3 路由 ──
            try:
                with st.status("🔄 四阶段流水线运行中...", expanded=True) as status:
                    # Phase 1
                    st.write("📋 **Phase 1**: 脚本精炼引擎运行中...")
                    cleaned_script = preprocess_script(raw_script)
                    st.session_state["cleaned_script"] = cleaned_script
                    phase1_result = execute_phase1(
                        cleaned_script, target_ip_style, final_api_key
                    )
                    st.session_state["phase1_result"] = phase1_result
                    st.write(
                        f"   ✅ Phase 1 完成 — "
                        f"提取 {len(phase1_result.get('hook_sentences', []))} 个引子句, "
                        f"{len(phase1_result.get('visual_constraints', []))} 条画面约束, "
                        f"{len(phase1_result.get('product_pitch', []))} 条带货金句"
                    )

                    # Phase 2
                    st.write("🌐 **Phase 2**: 翻译 + 分镜并发引擎运行中...")
                    phase2_result = execute_phase2(
                        phase1_result, cleaned_script, target_ip_style, final_api_key
                    )
                    st.session_state["phase2_result"] = phase2_result
                    trans_status = phase2_result.get("translation", {}).get("status", "?")
                    story_status = phase2_result.get("storyboard", {}).get("status", "?")
                    shot_count = phase2_result.get("storyboard", {}).get("shot_count", 0)
                    st.write(
                        f"   ✅ Phase 2 完成 — "
                        f"翻译通道: {trans_status}, 分镜通道: {story_status} ({shot_count} 个分镜)"
                    )

                    # Phase 3 路由
                    st.write("🎬 **Phase 3**: TTS 配音 + 视觉分发路由运行中...")
                    phase3_result = execute_phase3_routing(phase2_result)
                    st.session_state["phase3_result"] = phase3_result
                    visual_count = len(phase3_result.get("visual", []))
                    tts_count = len(phase3_result.get("tts", []))
                    video_count = sum(
                        1 for v in phase3_result.get("visual", [])
                        if v.get("type") == "video"
                    )
                    image_count = sum(
                        1 for v in phase3_result.get("visual", [])
                        if v.get("type") == "image"
                    )
                    st.write(
                        f"   ✅ Phase 3 完成 — "
                        f"TTS: {tts_count} 段配音, "
                        f"视觉路由: {visual_count} 个素材 "
                        f"({video_count} 视频 + {image_count} 图像)"
                    )

                    status.update(
                        label="✅ 前三阶段完成！请审核视觉素材。",
                        state="complete",
                    )

                st.session_state["pipeline_stage"] = "awaiting_review"
                st.rerun()

            except Exception as e:
                st.session_state["pipeline_error"] = str(e)
                st.error(f"❌ 流水线执行失败: {e}")

    # ── 品控审核阶段（Phase 3 之后）──
    elif stage == "awaiting_review":
        phase3_result = st.session_state.get("phase3_result", {})
        visual_candidates = phase3_result.get("visual", [])

        st.divider()
        st.subheader("👁 人机品控 — 视觉素材审核")
        st.markdown(
            f"共 **{len(visual_candidates)}** 个候选素材，"
            f"请逐条审核并勾选通过的素材。"
        )

        if visual_candidates:
            review_cols = st.columns(2)
            decisions = {}

            for idx, candidate in enumerate(visual_candidates):
                with review_cols[idx % 2]:
                    with st.container(border=True):
                        viz_type = candidate.get("type", "?").upper()
                        emoji_type = "🎥" if viz_type == "VIDEO" else "🖼"
                        st.markdown(f"**{emoji_type} [{idx + 1}] {viz_type}**")
                        st.caption(
                            f"时间戳: {candidate.get('duration_seconds', '?')}s"
                        )
                        st.caption(
                            f"Prompt: {candidate.get('prompt', 'N/A')[:120]}..."
                        )
                        st.caption(
                            f"路由原因: {candidate.get('route_reason', 'N/A')}"
                        )
                        approved = st.checkbox(
                            "确认采纳",
                            value=True,
                            key=f"review_{idx}",
                        )
                        if not approved:
                            reject_reason = st.text_input(
                                "驳回原因",
                                key=f"reject_reason_{idx}",
                                placeholder="输入驳回原因...",
                            )
                        else:
                            reject_reason = ""
                        decisions[idx] = {
                            "approved": approved,
                            "reject_reason": reject_reason if not approved else "",
                        }

            st.divider()

            # 醒目的阻断式审批闸门
            st.warning(
                "⚠️ **流水线已暂停！** 请人类指挥官逐条审核上述视觉候选素材，"
                "勾选通过的条目后，点击下方按钮放行。"
            )
            if st.button(
                "🛑 确认采纳视觉方案，进入第四阶段",
                type="primary",
                use_container_width=True,
            ):
                reviewed = []
                for idx, candidate in enumerate(visual_candidates):
                    dec = decisions.get(idx, {"approved": True, "reject_reason": ""})
                    candidate_copy = dict(candidate)
                    candidate_copy["review_status"] = (
                        "approved" if dec["approved"] else "rejected"
                    )
                    candidate_copy["reject_reason"] = dec.get("reject_reason", "")
                    reviewed.append(candidate_copy)

                st.session_state["reviewed_visuals"] = reviewed
                approved_count = sum(
                    1 for r in reviewed if r["review_status"] == "approved"
                )
                st.success(
                    f"品控完成！{approved_count}/{len(reviewed)} 个素材通过审核。"
                )

                # 继续执行 Phase 4
                with st.spinner("🔄 Phase 4 装配车间运行中..."):
                    try:
                        phase4_result = execute_phase4_assembly(
                            phase3_result,
                            st.session_state.get("cleaned_script", ""),
                        )
                        st.session_state["phase4_result"] = phase4_result
                        st.session_state["pipeline_stage"] = "awaiting_approval"
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Phase 4 执行失败: {e}")

    # ── 特效审批阶段（Phase 4 之后）──
    elif stage == "awaiting_approval":
        phase4_result = st.session_state.get("phase4_result", {})
        effects_plan = phase4_result.get("effects_plan", {})
        timeline = phase4_result.get("timeline", {})

        st.divider()
        st.subheader("🎛 最终审批 — 智能特效方案")

        # 特效方案展示
        eff_col1, eff_col2, eff_col3 = st.columns(3)

        with eff_col1:
            st.markdown("#### 🎵 BGM 推荐")
            bgm = effects_plan.get("recommended_bgm", {})
            st.metric("检测情绪", effects_plan.get("detected_emotion", "默认"))
            st.markdown(f"**曲目**: {bgm.get('name', 'N/A')}")
            st.markdown(f"**BPM**: {bgm.get('bpm', '?')}")
            st.markdown(f"**风格**: {bgm.get('style', '?')}")
            st.markdown(f"**音量**: {effects_plan.get('bgm_volume', 0.3) * 100:.0f}%")

        with eff_col2:
            st.markdown("#### 🎬 转场 + 关键帧")
            st.markdown(
                f"**转场数量**: {effects_plan.get('transition_count', 0)} 处"
            )
            kf = effects_plan.get("keyframe_plan", {})
            st.markdown(f"**关键帧策略**: {kf.get('strategy', '?')}")
            st.markdown(
                f"**缩放**: {kf.get('start_scale', 1.0)}x → "
                f"{kf.get('peak_scale', 1.3)}x"
            )
            st.markdown(f"**缓动**: {kf.get('easing', '?')}")

        with eff_col3:
            st.markdown("#### 🎨 调色 + 叠加")
            st.markdown(f"**调色预设**: {effects_plan.get('color_grading', '?')}")
            overlays = effects_plan.get("overlay_effects", [])
            if overlays:
                for ov in overlays:
                    st.markdown(f"- {ov}")
            else:
                st.caption("无叠加特效")

        # 时间轴摘要
        st.divider()
        st.markdown("#### ⏱ 时间轴摘要")
        tc1, tc2, tc3, tc4 = st.columns(4)
        with tc1:
            st.metric("总时长", f"{timeline.get('total_duration_seconds', 0)}s")
        with tc2:
            stats = timeline.get("alignment_stats", {})
            st.metric("音频片段", stats.get("audio_clips", 0))
        with tc3:
            st.metric("视觉片段", stats.get("video_clips", 0))
        with tc4:
            st.metric("字幕条目", stats.get("subtitle_clips", 0))

        # 审批决策
        st.divider()
        st.markdown("#### ✋ 请做出最终决策")

        approval_decision = st.radio(
            "特效方案审批",
            options=["确认 — 一键应用此方案", "修改 — 输入修改意见", "驳回 — 放弃此方案"],
            index=0,
            key="approval_radio",
        )

        feedback_text = ""
        if "修改" in approval_decision:
            feedback_text = st.text_area(
                "修改意见",
                placeholder="请输入需要调整的内容...",
                key="approval_feedback",
            )

        st.divider()

        # 醒目的阻断式审批闸门
        st.warning(
            "⚠️ **流水线已暂停！** 请人类指挥官审核上述特效方案，"
            "做出最终决策后点击下方按钮完成装配。"
        )
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 6])
        with col_btn1:
            if st.button(
                "🛑 确认特效方案，完成装配",
                type="primary",
                use_container_width=True,
            ):
                decision_map = {
                    "确认": "approved",
                    "修改": "pending_revision",
                    "驳回": "rejected",
                }
                human_decision = "确认"
                if "修改" in approval_decision:
                    human_decision = "修改"
                elif "驳回" in approval_decision:
                    human_decision = "驳回"

                final_status = decision_map.get(human_decision, "rejected")

                # 构建审批结果
                approval_result = {
                    "human_decision": human_decision,
                    "final_status": final_status,
                    "effects_plan_applied": (
                        effects_plan if final_status != "rejected" else None
                    ),
                    "human_feedback": feedback_text if feedback_text else "",
                }

                phase4_result["approval"] = approval_result
                st.session_state["phase4_result"] = phase4_result
                st.session_state["approval_decision"] = approval_result
                st.session_state["pipeline_stage"] = "video_review"
                st.rerun()

    # ── 最终成品审核阶段（Phase 4 之后的终极闭环）──
    elif stage == "video_review":
        st.divider()
        st.success("## 🎬 最终成品预览 — 真实 AI 生成内容")

        phase3_result = st.session_state.get("phase3_result", {})
        phase4_result = st.session_state.get("phase4_result", {})
        reviewed_visuals = st.session_state.get("reviewed_visuals", [])

        # ── 音频播放区 ──
        st.markdown("### 🎙 AI 配音（硅基流动 CosyVoice2）")
        tts_data = phase3_result.get("tts", [])
        live_audio_files = [
            t for t in tts_data
            if t.get("status") == "live" and t.get("audio_path", "").endswith(".mp3")
        ]
        fallback_audio = [
            t for t in tts_data
            if t.get("status") != "live" or not t.get("audio_path", "").endswith(".mp3")
        ]

        if live_audio_files:
            audio_cols = st.columns(min(len(live_audio_files), 3))
            for idx, audio in enumerate(live_audio_files):
                with audio_cols[idx % 3]:
                    audio_path = audio.get("audio_path", "")
                    st.caption(f"片段 {audio.get('segment_index', idx + 1)}: "
                               f"{audio.get('text', '')[:60]}...")
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 100:
                        try:
                            st.audio(audio_path, format="audio/mp3")
                        except Exception:
                            st.warning("⚠️ 音频加载失败")
                    else:
                        st.warning("⚠️ 音频文件为空或不存在")
        else:
            st.warning("⚠️ 没有真实 AI 配音数据。请检查硅基流动 API Key 配置。")

        if fallback_audio:
            with st.expander(f"📋 {len(fallback_audio)} 段降级配音详情", expanded=False):
                for fa in fallback_audio:
                    st.caption(
                        f"[{fa.get('status', '?')}] "
                        f"{fa.get('text', 'N/A')[:80]}..."
                    )

        st.divider()

        # ── 视觉成品展示区 ──
        st.markdown("### 🎥 AI 生成视觉素材（海螺AI MiniMax）")
        visuals_to_show = reviewed_visuals if reviewed_visuals else phase3_result.get(
            "visual", []
        )

        # 检查是否有真实图片/视频
        real_images = [
            v for v in visuals_to_show
            if v.get("type") == "image" and v.get("status") == "live"
            and v.get("file_path", "").endswith((".png", ".jpg", ".jpeg"))
        ]
        real_videos = [
            v for v in visuals_to_show
            if v.get("type") == "video" and v.get("status") == "live"
            and v.get("file_path", "").endswith(".mp4")
        ]
        fallback_visuals = [
            v for v in visuals_to_show
            if v.get("status") != "live"
            or not v.get("file_path", "").endswith((".png", ".jpg", ".jpeg", ".mp4"))
        ]

        if real_images or real_videos:
            # 真实视频（如果有）
            if real_videos:
                st.markdown("#### 🎬 AI 生成视频片段")
                for vid in real_videos:
                    st.caption(
                        f"Prompt: {vid.get('prompt', 'N/A')[:100]}..."
                    )
                    if os.path.exists(vid["file_path"]) and os.path.getsize(vid["file_path"]) > 1000:
                        try:
                            st.video(vid["file_path"])
                        except Exception:
                            st.warning("⚠️ 视频播放失败")
                    else:
                        st.caption(f"  状态: {vid.get('status', '?')} — 视频文件不可用")

            # 真实图片
            if real_images:
                st.markdown("#### 🖼 AI 生成图片")
                img_cols = st.columns(min(len(real_images), 3))
                for idx, img in enumerate(real_images):
                    with img_cols[idx % 3]:
                        st.caption(
                            f"时间戳: {img.get('duration_seconds', '?')}s"
                        )
                        if os.path.exists(img["file_path"]) and os.path.getsize(img["file_path"]) > 100:
                            try:
                                st.image(img["file_path"], use_container_width=True)
                            except Exception:
                                st.warning("⚠️ 图片加载失败")
                        else:
                            st.warning("⚠️ 图片文件为空或不存在")
                        st.caption(
                            f"Prompt: {img.get('prompt', 'N/A')[:80]}..."
                        )
        else:
            st.warning(
                "⚠️ 没有真实 AI 生成的视觉素材。"
                "请检查海螺AI (MiniMax) API Key 配置。"
            )

        if fallback_visuals:
            with st.expander(
                f"📋 {len(fallback_visuals)} 个降级/失败素材详情", expanded=False
            ):
                for fv in fallback_visuals:
                    st.caption(
                        f"[{fv.get('type', '?')}] status={fv.get('status', '?')} | "
                        f"{fv.get('prompt', 'N/A')[:100]}..."
                    )

        st.divider()

        # 阶段四结果摘要
        timeline = phase4_result.get("timeline", {})
        effects = phase4_result.get("effects_plan", {})
        stats = timeline.get("alignment_stats", {})

        with st.expander("📊 Phase 4 装配数据摘要", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("总时长", f"{timeline.get('total_duration_seconds', 0)}s")
            with c2:
                st.metric("音频片段", stats.get("audio_clips", 0))
            with c3:
                st.metric("视觉片段", stats.get("video_clips", 0))
            with c4:
                st.metric("BGM", effects.get("recommended_bgm", {}).get("name", "N/A"))

        st.divider()

        # 终极确认闸门
        st.warning(
            "⚠️ **最终审核闸门！** 请人类指挥官审核上方 AI 生成的音频和视觉素材，"
            "确认无误后点击下方按钮，系统将生成剪映底层草稿文件。"
        )
        if st.button(
            "🛑 视觉审核通过，生成剪映底层草稿文件！",
            type="primary",
            use_container_width=True,
        ):
            jianying_draft = _generate_jianying_draft(
                phase4_result,
                st.session_state.get("phase1_result", {}),
                st.session_state.get("phase2_result", {}),
            )
            st.session_state["jianying_draft"] = jianying_draft
            st.session_state["pipeline_stage"] = "complete"
            st.rerun()

    # ── 流水线完成 ──
    if st.session_state.get("pipeline_stage") == "complete":
        st.divider()
        st.success("## 🏁 全线流水线执行完毕！")

        phase1 = st.session_state.get("phase1_result", {})
        phase2 = st.session_state.get("phase2_result", {})
        phase3 = st.session_state.get("phase3_result", {})
        phase4 = st.session_state.get("phase4_result", {})
        approval = st.session_state.get("approval_decision", {})

        # 剪映底层草稿下载
        jianying_draft = st.session_state.get("jianying_draft", {})
        draft_path = jianying_draft.get("file_path", "")
        if draft_path and os.path.exists(draft_path):
            with open(draft_path, "r", encoding="utf-8") as f:
                draft_json = f.read()
            st.download_button(
                label="📥 下载剪映底层草稿 JSON",
                data=draft_json,
                file_name="jianying_draft.json",
                mime="application/json",
                type="primary",
            )
            st.caption(f"草稿已保存到: `{draft_path}`")

        # Tab 式结果展示
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Phase 1 脚本精炼",
            "🌐 Phase 2 翻译+分镜",
            "🎬 Phase 3 多模态",
            "⏱ Phase 4 装配",
            "📊 全链路 JSON",
        ])

        with tab1:
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown("#### 🔥 引子 / 冲突句")
                hooks = phase1.get("hook_sentences", [])
                if hooks:
                    for idx, s in enumerate(hooks, start=1):
                        st.markdown(f"> **{idx}.** {s}")
                else:
                    st.caption("（未提取到相关内容）")

            with col_b:
                st.markdown("#### 🎬 画面约束")
                visuals = phase1.get("visual_constraints", [])
                target_style = st.session_state.get("target_ip_style", "")
                if visuals:
                    for idx, v in enumerate(visuals, start=1):
                        if "整体视觉基调" in v and target_style in v:
                            st.markdown(f"> **{idx}.** {v} 🛡️")
                        else:
                            st.markdown(f"> **{idx}.** {v}")
                else:
                    st.caption("（未提取到相关内容）")

            with col_c:
                st.markdown("#### 💰 带货金句")
                pitches = phase1.get("product_pitch", [])
                if pitches:
                    for idx, p in enumerate(pitches, start=1):
                        st.markdown(f"> **{idx}.** {p}")
                else:
                    st.caption("（未提取到相关内容）")

        with tab2:
            translation = phase2.get("translation", {})
            storyboard = phase2.get("storyboard", {})

            st.markdown("#### 🌐 翻译通道")
            st.markdown(f"**状态**: {translation.get('status', 'N/A')}")
            st.markdown(f"**目标语言**: {translation.get('target_language', 'N/A')}")
            trans_pitches = translation.get("translated_pitches", [])
            if trans_pitches:
                for idx, tp in enumerate(trans_pitches, start=1):
                    st.markdown(f"> **{idx}.** {tp}")
            loc_notes = translation.get("localization_notes", [])
            if loc_notes:
                st.markdown("**本地化备注**:")
                for note in loc_notes:
                    st.markdown(f"- {note}")

            st.markdown("#### 🎬 分镜通道")
            st.markdown(f"**状态**: {storyboard.get('status', 'N/A')}")
            st.markdown(f"**分镜数量**: {storyboard.get('shot_count', 0)}")
            st.markdown(f"**全局风格备注**: {storyboard.get('global_style_note', '无')}")
            prompts = storyboard.get("storyboard_prompts", [])
            if prompts:
                for idx, sp in enumerate(prompts, start=1):
                    st.markdown(f"> **镜头 {idx}**: {sp}")

        with tab3:
            tts_data = phase3.get("tts", [])
            visual_data = phase3.get("visual", [])
            reviewed = st.session_state.get("reviewed_visuals", visual_data)

            st.markdown("#### 🎙 TTS 配音")
            if tts_data:
                for idx, t in enumerate(tts_data, start=1):
                    st.markdown(
                        f"> **{idx}.** {t.get('text', '')} "
                        f"({t.get('duration_seconds', 0)}s)"
                    )
            else:
                st.caption("（无 TTS 数据）")

            st.markdown("#### 🎥 视觉路由结果（品控后）")
            if reviewed:
                for idx, v in enumerate(reviewed, start=1):
                    status_icon = "✅" if v.get("review_status") == "approved" else "❌"
                    st.markdown(
                        f"> **{idx}.** {status_icon} "
                        f"[{v.get('type', '?').upper()}] "
                        f"{v.get('prompt', 'N/A')[:100]}..."
                    )
                    if v.get("review_status") == "rejected":
                        st.caption(f"   驳回原因: {v.get('reject_reason', '?')}")

        with tab4:
            timeline = phase4.get("timeline", {})
            effects = phase4.get("effects_plan", {})
            appr = approval or phase4.get("approval", {})

            st.markdown("#### ⏱ 时间轴")
            st.json({
                "total_duration_s": timeline.get("total_duration_seconds"),
                "alignment_stats": timeline.get("alignment_stats"),
            })

            st.markdown("#### 🎛 特效方案")
            st.markdown(f"**情绪**: {effects.get('detected_emotion')}")
            st.markdown(f"**BGM**: {effects.get('recommended_bgm', {}).get('name')}")
            st.markdown(f"**调色**: {effects.get('color_grading')}")

            st.markdown("#### ✋ 审批结果")
            st.markdown(f"**决策**: {appr.get('human_decision', 'N/A')}")
            st.markdown(f"**状态**: {appr.get('final_status', 'N/A')}")
            if appr.get("human_feedback"):
                st.markdown(f"**反馈**: {appr['human_feedback']}")

        with tab5:
            st.markdown("#### 📊 全链路结构化数据")
            full_pipeline = {
                "phase1_script_refinement": phase1,
                "phase2_translation_storyboard": {
                    "translation": phase2.get("translation"),
                    "storyboard": phase2.get("storyboard"),
                },
                "phase3_multimodal": {
                    "tts_count": len(phase3.get("tts", [])),
                    "visual_count": len(phase3.get("visual", [])),
                    "reviewed_visuals": st.session_state.get("reviewed_visuals", []),
                },
                "phase4_assembly": {
                    "timeline_summary": phase4.get("timeline", {}).get("alignment_stats"),
                    "effects_plan": phase4.get("effects_plan"),
                    "approval": approval or phase4.get("approval"),
                },
            }
            st.json(full_pipeline)

            # 预处理对比
            with st.expander("📋 查看预处理前后对比", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("原始输入")
                    st.text(raw_script)
                with c2:
                    st.caption("预处理后")
                    st.text(st.session_state.get("cleaned_script", ""))


# ============================================================================
# 程序入口
# ============================================================================

if __name__ == "__main__":
    main()
