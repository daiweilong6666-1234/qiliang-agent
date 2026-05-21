"""
================================================================================
 启量 Agent — 第四阶段：半自动装配车间
 独立模块（与 Phase 1 / 2 / 3 完全解耦）
 核心能力：时间轴对齐 · 智能特效方案 · 人机协作最终防线
================================================================================
"""

import json
import os
import time
import hashlib
from datetime import datetime
from typing import Optional

# ============================================================================
# 全局配置
# ============================================================================

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "phase4_output")
TIMELINE_DIR = os.path.join(OUTPUT_DIR, "timeline")
EFFECTS_DIR = os.path.join(OUTPUT_DIR, "effects")

# 字幕样式预设
SUBTITLE_STYLE = {
    "font": "PingFang SC Bold",
    "font_size": 48,
    "color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 2.0,
    "alignment": "center",
    "position": "bottom",
    "margin_bottom_px": 80,
}

# BGM 推荐库（按情绪分类）
BGM_LIBRARY = {
    "悬疑": [
        {"name": "Mystery_Reveal_01", "bpm": 90, "style": "cinematic_tension"},
        {"name": "Dark_Secrets_02", "bpm": 85, "style": "ambient_drone"},
    ],
    "激情": [
        {"name": "Epic_Launch_01", "bpm": 128, "style": "epic_orchestral"},
        {"name": "Power_Up_02", "bpm": 140, "style": "electronic_rock"},
    ],
    "温馨": [
        {"name": "Warm_Moments_01", "bpm": 75, "style": "acoustic_pop"},
        {"name": "Soft_Touch_02", "bpm": 80, "style": "lofi_chill"},
    ],
    "科技": [
        {"name": "Cyber_Pulse_01", "bpm": 110, "style": "synthwave"},
        {"name": "Digital_Dream_02", "bpm": 100, "style": "future_bass"},
    ],
    "搞笑": [
        {"name": "Funny_Bounce_01", "bpm": 120, "style": "comedy_funk"},
        {"name": "Slapstick_02", "bpm": 115, "style": "cartoon_jazz"},
    ],
    "默认": [
        {"name": "Chill_Vlog_01", "bpm": 95, "style": "lofi_hiphop"},
        {"name": "Light_Mood_02", "bpm": 85, "style": "ambient_pop"},
    ],
}

# 转场方案库（按情绪分类）
TRANSITION_LIBRARY = {
    "悬疑": ["fade_to_black", "slow_zoom_in", "glitch_dissolve"],
    "激情": ["whip_pan", "speed_ramp", "flash_white"],
    "温馨": ["soft_crossfade", "gentle_blur", "slow_fade"],
    "科技": ["glitch_shift", "digital_wipe", "hologram_fade"],
    "搞笑": ["pop_bounce", "spin_out", "cartoon_wipe"],
    "默认": ["crossfade", "dip_to_black", "smooth_cut"],
}

# 关键帧方案
KEYFRAME_PRESETS = {
    "product_showcase": {"start_scale": 1.0, "peak_scale": 1.8, "duration_ms": 1200},
    "hook_intro": {"start_scale": 1.5, "peak_scale": 1.0, "duration_ms": 800},
    "suspense_build": {"start_scale": 1.0, "peak_scale": 2.0, "duration_ms": 2000},
    "quick_cut": {"start_scale": 1.0, "peak_scale": 1.0, "duration_ms": 300},
    "default": {"start_scale": 1.0, "peak_scale": 1.3, "duration_ms": 1000},
}


# ============================================================================
# 辅助工具
# ============================================================================

def ensure_output_dirs():
    """确保所有输出目录存在。"""
    os.makedirs(TIMELINE_DIR, exist_ok=True)
    os.makedirs(EFFECTS_DIR, exist_ok=True)


def generate_id(prefix: str, seed: str) -> str:
    """生成短唯一 ID。"""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{h}"


# ============================================================================
# 模块一：时间轴对齐引擎
# ============================================================================

def calculate_subtitle_timing(
    text: str,
    start_ms: int,
    chars_per_second: float = 4.0,
) -> dict:
    """
    根据文本内容和起始时间，计算字幕的显示时间区间。

    参数：
      text             — 字幕文本内容。
      start_ms         — 字幕开始时间（毫秒）。
      chars_per_second — 每秒展示的字数（中文默认每秒 4 字）。

    返回：
      { text, start_ms, end_ms, duration_ms }
    """
    char_count = len(text)
    duration_ms = int((char_count / chars_per_second) * 1000)
    # 最小显示时长 500ms，确保极短字幕也能被看到
    duration_ms = max(duration_ms, 500)
    end_ms = start_ms + duration_ms

    return {
        "text": text,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "duration_ms": duration_ms,
        "char_count": char_count,
    }


def build_timeline(
    tts_segments: list,
    visual_shots: list,
    project_name: str = "qiliang_agent_video",
) -> dict:
    """
    时间轴对齐引擎 —— 将 TTS 音频和视觉素材对齐到统一的毫秒级时间轴。

    核心逻辑：
      1. 以 TTS 片段作为时间轴主线（音频决定节奏）。
      2. 每个视觉素材映射到对应时间段的 TTS 片段上。
      3. 为每段 TTS 文本自动生成字幕轨道。
      4. 输出结构化的 Timeline JSON 配置文件。

    参数：
      tts_segments — TTS 输出列表，每项含 audio_path 和 duration_seconds。
      visual_shots — 视觉素材列表，每项含 file_path、type、duration_seconds。

    返回：
      完整的 Timeline JSON 配置字典。
    """
    ensure_output_dirs()

    timeline = {
        "project": project_name,
        "created_at": datetime.now().isoformat(),
        "version": "1.0.0",
        "timeline_resolution": "milliseconds",
        "total_duration_ms": 0,
        "tracks": {
            "video": [],       # 视频/图像轨道
            "audio": [],       # 配音轨道
            "subtitle": [],    # 字幕轨道
            "bgm": [],         # 背景音乐轨道（占位）
        },
    }

    current_ms = 0
    max_tts = len(tts_segments)
    max_visual = len(visual_shots)

    # 以 TTS 片段为锚点推进时间轴
    for idx in range(max_tts):
        tts = tts_segments[idx]

        # ── TTS 音频时长（毫秒）──
        tts_duration_s = tts.get("duration_seconds", 2.0)
        tts_duration_ms = int(tts_duration_s * 1000)
        tts_end_ms = current_ms + tts_duration_ms

        tts_text = tts.get("text", "")

        # ── 音频轨道 ──
        audio_clip = {
            "clip_id": generate_id("audio", f"{idx}_{tts_text}"),
            "index": idx,
            "type": "tts_audio",
            "file_path": tts.get("audio_path", ""),
            "start_ms": current_ms,
            "end_ms": tts_end_ms,
            "duration_ms": tts_duration_ms,
            "text": tts_text,
            "voice_id": tts.get("voice_id", "default"),
        }
        timeline["tracks"]["audio"].append(audio_clip)

        # ── 字幕轨道 ──
        subtitle = calculate_subtitle_timing(
            text=tts_text,
            start_ms=current_ms,
        )
        subtitle["clip_id"] = generate_id("sub", f"{idx}_{tts_text}")
        subtitle["index"] = idx
        subtitle["style"] = SUBTITLE_STYLE
        timeline["tracks"]["subtitle"].append(subtitle)

        # ── 视觉轨道（映射到对应 TTS 片段）──
        if idx < max_visual:
            visual = visual_shots[idx]
            visual_clip = {
                "clip_id": generate_id("visual", f"{idx}_{visual.get('prompt', '')}"),
                "index": idx,
                "type": visual.get("type", "image"),
                "file_path": visual.get("file_path", ""),
                "start_ms": current_ms,
                "end_ms": tts_end_ms,
                "duration_ms": tts_duration_ms,
                "prompt": visual.get("prompt", ""),
                "route_reason": visual.get("route_reason", ""),
            }
            timeline["tracks"]["video"].append(visual_clip)
        elif idx < max_visual + 3:
            # 如果视觉素材不够，用最后一张图像撑满剩余时间
            last_visual = visual_shots[-1] if visual_shots else {"type": "image", "file_path": "", "prompt": ""}
            visual_clip = {
                "clip_id": generate_id("visual", f"padding_{idx}"),
                "index": idx,
                "type": last_visual.get("type", "image"),
                "file_path": last_visual.get("file_path", ""),
                "start_ms": current_ms,
                "end_ms": tts_end_ms,
                "duration_ms": tts_duration_ms,
                "prompt": last_visual.get("prompt", ""),
                "note": "填充素材（视觉素材不足，复用最后一张）",
            }
            timeline["tracks"]["video"].append(visual_clip)

        # 推进时间指针
        current_ms = tts_end_ms

    timeline["total_duration_ms"] = current_ms
    timeline["total_duration_seconds"] = round(current_ms / 1000, 2)

    # ── 对齐统计 ──
    timeline["alignment_stats"] = {
        "audio_clips": len(timeline["tracks"]["audio"]),
        "video_clips": len(timeline["tracks"]["video"]),
        "subtitle_clips": len(timeline["tracks"]["subtitle"]),
        "audio_video_ratio": (
            f"{len(timeline['tracks']['audio'])}:{len(timeline['tracks']['video'])}"
        ),
        "max_misalignment_ms": max(
            0,
            abs(
                len(timeline["tracks"]["audio"]) * tts_duration_ms
                - len(timeline["tracks"]["video"]) * tts_duration_ms
            ),
        ),
    }

    # ── 保存 Timeline JSON ──
    timeline_path = os.path.join(
        TIMELINE_DIR,
        f"timeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    print(f"\n  [时间轴] Timeline JSON 已保存: {timeline_path}")
    print(f"  [时间轴] 总时长: {timeline['total_duration_seconds']}s")
    print(f"  [时间轴] 音频片段: {timeline['alignment_stats']['audio_clips']}")
    print(f"  [时间轴] 视觉片段: {timeline['alignment_stats']['video_clips']}")
    print(f"  [时间轴] 字幕条目: {timeline['alignment_stats']['subtitle_clips']}")

    return timeline


# ============================================================================
# 模块二：智能特效方案
# ============================================================================

def detect_emotion(script_text: str) -> str:
    """
    根据剧本关键词做情绪检测（规则引擎）。
    返回情绪标签，用于匹配 BGM / 转场 / 关键帧预设。

    真实项目中这里应该接一个 NLP 情绪分类模型，
    当前用规则引擎做轻量实现。
    """
    text_lower = script_text.lower()

    emotion_rules = [
        ("悬疑", ["秘密", "背后", "不为人知", "揭秘", "隐藏", "真相", "竟然", "原来",
                  "secret", "hidden", "mystery", "reveal"]),
        ("激情", ["限时", "抢购", "爆炸", "疯狂", "震撼", "史无前例", "超值",
                  "epic", "crazy", "shocking", "limited"]),
        ("温馨", ["温暖", "家", "陪伴", "幸福", "甜蜜", "回忆", "日常",
                  "warm", "family", "sweet", "memories"]),
        ("科技", ["科技", "智能", "AI", "黑科技", "纳米", "数据", "芯片",
                  "tech", "smart", "digital", "cyber"]),
        ("搞笑", ["搞笑", "笑死", "离谱", "沙雕", "哈哈哈", "搞笑",
                  "funny", "lol", "meme", "joke"]),
    ]

    for emotion, keywords in emotion_rules:
        for kw in keywords:
            if kw in text_lower:
                return emotion

    return "默认"


def generate_effects_plan(
    script_text: str,
    total_duration_ms: int,
    shot_count: int,
) -> dict:
    """
    智能特效方案引擎 —— 根据素材内容自动生成一套爆款特效方案。

    输出包含：
      - recommended_bgm: 推荐背景音乐
      - transition_plan: 转场方案
      - keyframe_plan: 关键帧缩放策略
      - color_grading: 调色预设
      - overlay_effects: 叠加特效建议

    参数：
      script_text        — 完整剧本文本（用于情绪检测）。
      total_duration_ms  — 视频总时长（毫秒）。
      shot_count         — 视觉素材总数。
    """
    emotion = detect_emotion(script_text)

    # ── 选 BGM ──
    bgm_options = BGM_LIBRARY.get(emotion, BGM_LIBRARY["默认"])
    recommended_bgm = bgm_options[0]

    # ── 选转场方案 ──
    transition_options = TRANSITION_LIBRARY.get(emotion, TRANSITION_LIBRARY["默认"])
    transition_plan = []
    for i in range(shot_count - 1):
        trans = transition_options[i % len(transition_options)]
        from_clip = i
        to_clip = i + 1
        transition_plan.append({
            "from_clip_index": from_clip,
            "to_clip_index": to_clip,
            "type": trans,
            "duration_ms": 300,  # 默认转场 300ms
        })

    # ── 选关键帧方案 ──
    if shot_count == 1:
        keyframe_strategy = "quick_cut"
    elif shot_count <= 3:
        keyframe_strategy = "hook_intro"
    elif "限时" in script_text or "优惠" in script_text:
        keyframe_strategy = "product_showcase"
    elif emotion == "悬疑":
        keyframe_strategy = "suspense_build"
    else:
        keyframe_strategy = "default"

    keyframe_config = KEYFRAME_PRESETS.get(keyframe_strategy, KEYFRAME_PRESETS["default"])
    keyframe_plan = {
        "strategy": keyframe_strategy,
        "start_scale": keyframe_config["start_scale"],
        "peak_scale": keyframe_config["peak_scale"],
        "duration_ms": keyframe_config["duration_ms"],
        "apply_to_clips": list(range(shot_count)),
        "easing": "ease_in_out_cubic",
    }

    # ── 调色预设 ──
    color_grading_presets = {
        "悬疑": "dark_moody_teal_orange",
        "激情": "vibrant_contrast_boost",
        "温馨": "warm_golden_soft_glow",
        "科技": "cyberpunk_blue_purple",
        "搞笑": "bright_pop_saturated",
        "默认": "natural_balanced",
    }
    color_grading = color_grading_presets.get(emotion, color_grading_presets["默认"])

    # ── 叠加特效 ──
    overlay_effects_map = {
        "悬疑": ["vignette_darken", "film_grain_subtle"],
        "激情": ["lens_flare", "motion_blur_burst"],
        "温馨": ["soft_glow", "light_leak_warm"],
        "科技": ["scan_lines", "holographic_overlay"],
        "搞笑": ["bounce_zoom", "cartoon_sparkle"],
        "默认": [],
    }
    overlay_effects = overlay_effects_map.get(emotion, [])

    effects_plan = {
        "detected_emotion": emotion,
        "recommended_bgm": recommended_bgm,
        "bgm_start_ms": 0,
        "bgm_end_ms": total_duration_ms,
        "bgm_volume": 0.3,  # BGM 音量 30%，不压过配音
        "transition_plan": transition_plan,
        "transition_count": len(transition_plan),
        "keyframe_plan": keyframe_plan,
        "color_grading": color_grading,
        "overlay_effects": overlay_effects,
        "global_effects_note": (
            f"[{emotion}风格] BGM: {recommended_bgm['name']} | "
            f"调色: {color_grading} | "
            f"关键帧策略: {keyframe_strategy}"
        ),
    }

    return effects_plan


# ============================================================================
# 模块三：人机协作最终防线
# ============================================================================

def human_final_approval(effects_plan: dict) -> dict:
    """
    人机协作最终防线 —— 注入人类灵魂的最后一道审批。

    流程：
      1. 在控制台打印完整的特效方案。
      2. 使用 input() 暂停，等待人类指挥官决策。
      3. 人类输入"确认" → 方案通过，写入最终装配日志。
      4. 人类输入修改意见 → 记录意见，标记待修改。
      5. 人类输入"驳回" → 方案废弃，返回失败状态。

    参数：
      effects_plan — 智能特效方案字典。

    返回：
      含 decision 字段的审批结果字典。
    """
    print(f"\n{'=' * 70}")
    print(f"  [FINAL GATE] 人机协作最终防线 — 特效方案审批")
    print(f"{'=' * 70}")
    print()
    print(f"  检测到的情绪基调: {effects_plan['detected_emotion']}")
    print(f"  推荐 BGM: {effects_plan['recommended_bgm']['name']}")
    print(f"    - BPM: {effects_plan['recommended_bgm']['bpm']}")
    print(f"    - 风格: {effects_plan['recommended_bgm']['style']}")
    print(f"    - 音量: {effects_plan['bgm_volume'] * 100:.0f}% (不压配音)")
    print()
    print(f"  转场方案 ({effects_plan['transition_count']} 处转场):")
    for t in effects_plan['transition_plan']:
        print(f"    [{t['from_clip_index']} -> {t['to_clip_index']}] "
              f"{t['type']} ({t['duration_ms']}ms)")
    print()
    print(f"  关键帧方案:")
    print(f"    - 策略: {effects_plan['keyframe_plan']['strategy']}")
    print(f"    - 缩放: {effects_plan['keyframe_plan']['start_scale']}x "
          f"-> {effects_plan['keyframe_plan']['peak_scale']}x")
    print(f"    - 缓动: {effects_plan['keyframe_plan']['easing']}")
    print()
    print(f"  调色预设: {effects_plan['color_grading']}")
    print(f"  叠加特效: {', '.join(effects_plan['overlay_effects']) if effects_plan['overlay_effects'] else '无'}")
    print()
    print(f"  综合备注: {effects_plan['global_effects_note']}")
    print()
    print(f"{'─' * 70}")
    print(f"  请输入你的决策:")
    print(f"    '确认'  — 一键应用此方案")
    print(f"    '修改'  — 输入修改意见")
    print(f"    '驳回'  — 放弃此方案，重新生成")
    print(f"{'─' * 70}")

    decision = input("  >>> ").strip()

    approval_result = {
        "timestamp": datetime.now().isoformat(),
        "human_decision": decision,
        "effects_plan_applied": None,
        "final_status": None,
    }

    if decision == "确认":
        approval_result["effects_plan_applied"] = effects_plan
        approval_result["final_status"] = "approved"
        print(f"\n  [OK] 方案已确认！特效方案将自动应用到最终装配。")

    elif decision == "修改":
        feedback = input("  >>> 请输入修改意见: ").strip()
        # 将修改意见嵌入方案中，供后续人工或二次生成参考
        effects_plan["human_feedback"] = feedback
        effects_plan["status"] = "pending_revision"
        approval_result["effects_plan_applied"] = effects_plan
        approval_result["final_status"] = "pending_revision"
        approval_result["human_feedback"] = feedback
        print(f"\n  [WARN] 已记录修改意见: {feedback}")
        print(f"  [WARN] 方案已标记为待修改，请在后续流程中根据反馈调整。")

    elif decision == "驳回":
        approval_result["effects_plan_applied"] = None
        approval_result["final_status"] = "rejected"
        print(f"\n  [X] 方案已驳回。请调整参数后重新生成特效方案。")

    else:
        # 未知输入，默认驳回
        approval_result["effects_plan_applied"] = None
        approval_result["final_status"] = "rejected"
        approval_result["reject_reason"] = f"未知输入: {decision}"
        print(f"\n  [X] 无法识别输入 '{decision}'，默认驳回。")

    return approval_result


# ============================================================================
# 主流程编排
# ============================================================================

def run_phase4_assembly(
    tts_segments: list,
    visual_shots: list,
    script_text: str,
    skip_human_review: bool = False,
) -> dict:
    """
    第四阶段完整流水线：
      时间轴对齐 → 智能特效方案 → 人机审批 → 最终装配日志。

    参数：
      tts_segments      — TTS 配音片段列表。
      visual_shots      — 视觉素材列表。
      script_text       — 完整剧本文本。
      skip_human_review — 跳过人工审批（仅自动化测试）。

    返回：
      完整的装配结果字典。
    """
    ensure_output_dirs()

    print("\n" + "=" * 70)
    print("  启量 Agent — 第四阶段 半自动装配车间")
    print(f"  启动时间: {datetime.now().isoformat()}")
    print("=" * 70)

    assembly_result = {
        "pipeline": "phase4_assembly",
        "timestamp": datetime.now().isoformat(),
        "timeline": None,
        "effects_plan": None,
        "approval": None,
        "final_log": None,
    }

    # ── 步骤 1：时间轴对齐 ──
    print(f"\n[1/3] 时间轴对齐引擎启动...")
    timeline = build_timeline(
        tts_segments=tts_segments,
        visual_shots=visual_shots,
    )
    assembly_result["timeline"] = timeline

    # ── 步骤 2：智能特效方案 ──
    print(f"\n[2/3] 智能特效方案生成中...")
    effects_plan = generate_effects_plan(
        script_text=script_text,
        total_duration_ms=timeline["total_duration_ms"],
        shot_count=len(timeline["tracks"]["video"]),
    )

    # 保存特效方案 JSON
    effects_path = os.path.join(
        EFFECTS_DIR,
        f"effects_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(effects_path, "w", encoding="utf-8") as f:
        json.dump(effects_plan, f, ensure_ascii=False, indent=2)
    print(f"  [效果] 特效方案已保存: {effects_path}")

    assembly_result["effects_plan"] = effects_plan

    # ── 步骤 3：人机协作审批 ──
    print(f"\n[3/3] 人机协作最终防线...")
    if skip_human_review:
        approval = {
            "timestamp": datetime.now().isoformat(),
            "human_decision": "auto_approved",
            "effects_plan_applied": effects_plan,
            "final_status": "approved_auto",
        }
        print(f"\n  [OK] 自动化模式：方案自动通过。")
    else:
        approval = human_final_approval(effects_plan)

    assembly_result["approval"] = approval

    # ── 最终装配日志 ──
    final_log = {
        "assembly_id": generate_id("assembly", f"{datetime.now().isoformat()}"),
        "completed_at": datetime.now().isoformat(),
        "final_status": approval["final_status"],
        "summary": {
            "total_duration_s": timeline["total_duration_seconds"],
            "audio_clips": timeline["alignment_stats"]["audio_clips"],
            "video_clips": timeline["alignment_stats"]["video_clips"],
            "subtitle_entries": timeline["alignment_stats"]["subtitle_clips"],
            "transitions": effects_plan["transition_count"],
            "bgm": effects_plan["recommended_bgm"]["name"],
            "color_grading": effects_plan["color_grading"],
            "emotion": effects_plan["detected_emotion"],
            "human_decision": approval["human_decision"],
        },
        "output_files": {
            "timeline_json": os.path.join(TIMELINE_DIR, os.listdir(TIMELINE_DIR)[-1]) if os.listdir(TIMELINE_DIR) else "",
            "effects_plan_json": effects_path,
        },
    }

    # 保存最终装配日志
    log_path = os.path.join(OUTPUT_DIR, "final_assembly_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(final_log, f, ensure_ascii=False, indent=2)

    assembly_result["final_log"] = final_log

    # ── 打印装配成功日志 ──
    print(f"\n{'=' * 70}")
    print(f"  [ASSEMBLY COMPLETE] 最终装配日志")
    print(f"{'=' * 70}")
    print(f"  装配 ID: {final_log['assembly_id']}")
    print(f"  完成时间: {final_log['completed_at']}")
    print(f"  最终状态: {final_log['final_status']}")
    print(f"  总时长: {final_log['summary']['total_duration_s']}s")
    print(f"  音频片段: {final_log['summary']['audio_clips']}")
    print(f"  视觉片段: {final_log['summary']['video_clips']}")
    print(f"  字幕条目: {final_log['summary']['subtitle_entries']}")
    print(f"  转场数量: {final_log['summary']['transitions']}")
    print(f"  BGM: {final_log['summary']['bgm']}")
    print(f"  调色: {final_log['summary']['color_grading']}")
    print(f"  情绪: {final_log['summary']['emotion']}")
    print(f"  审批决定: {final_log['summary']['human_decision']}")
    print(f"{'=' * 70}\n")

    return assembly_result


# ============================================================================
# 独立测试入口
# ============================================================================

if __name__ == "__main__":
    # ── 模拟 Phase 3 输出的测试数据 ──
    mock_tts_segments = [
        {
            "audio_path": "phase3_output/audio/tts_seg_001.wav",
            "duration_seconds": 2.5,
            "text": "你有没有想过，为什么超市里的苹果永远那么亮？",
            "voice_id": "default_female_cn",
        },
        {
            "audio_path": "phase3_output/audio/tts_seg_002.wav",
            "duration_seconds": 2.0,
            "text": "其实背后藏着一个不为人知的保鲜黑科技！",
            "voice_id": "default_female_cn",
        },
        {
            "audio_path": "phase3_output/audio/tts_seg_003.wav",
            "duration_seconds": 2.8,
            "text": "这款保鲜喷雾，喷一下就能让水果发光7天！",
            "voice_id": "default_female_cn",
        },
        {
            "audio_path": "phase3_output/audio/tts_seg_004.wav",
            "duration_seconds": 2.3,
            "text": "限时特惠，前100名下单立减50元！",
            "voice_id": "default_female_cn",
        },
    ]

    mock_visual_shots = [
        {
            "type": "video",
            "file_path": "phase3_output/visual/video_apple_closeup.mp4",
            "duration_seconds": 5,
            "prompt": "Close-up shot, glossy red apple, 3D animated style",
            "route_reason": "[黄金30s内] 强制视频",
        },
        {
            "type": "video",
            "file_path": "phase3_output/visual/video_supermarket_aisle.mp4",
            "duration_seconds": 12,
            "prompt": "Medium shot, supermarket aisle, bright lights",
            "route_reason": "[黄金30s内] 强制视频",
        },
        {
            "type": "image",
            "file_path": "phase3_output/visual/image_before_after.png",
            "duration_seconds": 35,
            "prompt": "Split screen, before and after comparison",
            "route_reason": "[30s后] 强制图像",
        },
        {
            "type": "image",
            "file_path": "phase3_output/visual/image_product_hero.png",
            "duration_seconds": 48,
            "prompt": "Product beauty shot, white pedestal",
            "route_reason": "[30s后] 强制图像",
        },
    ]

    mock_script = """
你有没有想过，为什么超市里的苹果永远那么亮？
其实背后藏着一个不为人知的保鲜黑科技！
这款保鲜喷雾，喷一下就能让水果发光7天！
限时特惠，前100名下单立减50元！
"""

    print("\n" + "=" * 70)
    print("  启量 Agent — 第四阶段 半自动装配 独立功能测试")
    print("=" * 70)

    # ── 子测试 1：时间轴对齐 ──
    print("\n[子测试 1] 时间轴对齐引擎")
    print("-" * 40)
    timeline = build_timeline(mock_tts_segments, mock_visual_shots)
    assert timeline["total_duration_ms"] > 0
    assert len(timeline["tracks"]["audio"]) == 4
    assert len(timeline["tracks"]["subtitle"]) == 4
    assert len(timeline["tracks"]["video"]) == 4
    print("  -> 时间轴对齐验证通过")

    # ── 子测试 2：智能特效方案 ──
    print("\n[子测试 2] 智能特效方案")
    print("-" * 40)
    effects = generate_effects_plan(
        mock_script,
        timeline["total_duration_ms"],
        len(timeline["tracks"]["video"]),
    )
    assert effects["detected_emotion"] in ["悬疑", "激情", "温馨", "科技", "搞笑", "默认"]
    assert effects["recommended_bgm"]["name"]
    assert len(effects["transition_plan"]) > 0
    print(f"  -> 情绪检测: {effects['detected_emotion']}")
    print(f"  -> BGM: {effects['recommended_bgm']['name']}")
    print(f"  -> 转场数: {effects['transition_count']}")
    print("  -> 特效方案生成验证通过")

    # ── 完整流水线（跳过人工审批，自动化测试）──
    print("\n[完整流水线]")
    print("-" * 40)
    result = run_phase4_assembly(
        tts_segments=mock_tts_segments,
        visual_shots=mock_visual_shots,
        script_text=mock_script,
        skip_human_review=True,
    )

    assert result["timeline"] is not None
    assert result["effects_plan"] is not None
    assert result["approval"]["final_status"] == "approved_auto"
    assert result["final_log"]["final_status"] == "approved_auto"
    print("\n  -> 完整流水线验证通过")

    # ── 输出文件统计 ──
    print(f"\n{'=' * 70}")
    print(f"  输出文件统计")
    print(f"{'=' * 70}")
    total_files = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        level = root.replace(OUTPUT_DIR, "").count(os.sep)
        indent = "  " * level
        print(f"  {indent}{os.path.basename(root)}/")
        for file in files:
            print(f"  {indent}  {file}")
            total_files += 1
    print(f"\n  总输出文件数: {total_files}")
    print(f"  全部测试通过！")
