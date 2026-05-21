"""
================================================================================
 启量 Agent — 第三阶段：多模态视觉铸造与品控车间
 独立模块（与 Phase 1 / Phase 2 完全解耦）
 核心能力：TTS 配音 · 视觉分发路由 · 人机协作品控
================================================================================
"""

import os
import json
import time
import hashlib
from datetime import datetime

# ============================================================================
# 全局配置
# ============================================================================

# 模拟输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "phase3_output")

# 音频文件模拟保存路径
AUDIO_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "audio")

# 视觉素材模拟保存路径
VISUAL_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "visual")

# 黄金 30 秒分界线（秒）
GOLDEN_30S_THRESHOLD = 30


# ============================================================================
# 模块一：TTS 配音通道
# ============================================================================

def ensure_output_dirs():
    """确保所有输出目录存在。"""
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(VISUAL_OUTPUT_DIR, exist_ok=True)


def text_to_speech(
    text: str,
    voice_id: str = "default_female_cn",
    speed: float = 1.0,
    audio_format: str = "wav",
) -> dict:
    """
    TTS 文本转语音函数。
    当前为模拟实现（Mock），预留了调用语音大模型 API 的接口位置。

    参数：
      text      — 需要转为语音的文本内容。
      voice_id  — 音色 ID，默认 "default_female_cn"。
      speed     — 语速倍率，1.0 为正常语速。
      audio_format — 输出音频格式，默认 "wav"。

    返回：
      字典，包含：
        - audio_path: 模拟的音频文件保存路径。
        - duration_seconds: 估算的音频时长（秒）。
        - text_length: 输入文本的字符数。
        - voice_id: 使用的音色 ID。
        - status: 状态标记（mock / live）。
    """
    ensure_output_dirs()

    # ── 估算音频时长（中文大约每秒 4 个字）──
    char_count = len(text)
    estimated_duration = round(char_count / 4.0, 2)

    # ── 生成唯一文件名（基于文本哈希 + 时间戳）──
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tts_{voice_id}_{timestamp}_{text_hash}.{audio_format}"
    audio_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    # ── 模拟生成音频文件（写入占位内容）──
    # TODO: 替换为真实的语音大模型 API 调用。
    # 接口预留位置 —— 将 text / voice_id / speed 传入以下 API：
    #
    #   response = tts_api.generate(
    #       text=text,
    #       voice=voice_id,
    #       speed=speed,
    #       format=audio_format,
    #   )
    #   with open(audio_path, "wb") as f:
    #       f.write(response.audio_bytes)
    #
    with open(audio_path, "w", encoding="utf-8") as f:
        f.write(f"# MOCK TTS AUDIO FILE\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Voice: {voice_id} | Speed: {speed}x\n")
        f.write(f"# Estimated Duration: {estimated_duration}s\n")
        f.write(f"# Text: {text[:100]}...\n")

    return {
        "audio_path": audio_path,
        "duration_seconds": estimated_duration,
        "text_length": char_count,
        "voice_id": voice_id,
        "status": "mock",  # 切换为 "live" 时表示已接入真实 API
    }


def batch_tts(text_segments: list, voice_id: str = "default_female_cn") -> list:
    """
    批量 TTS 处理：为多段文本分别生成配音。

    参数：
      text_segments — 文本片段列表，每段是一个字符串。
      voice_id      — 统一使用的音色 ID。

    返回：
      每段文本的 TTS 结果字典列表。
    """
    results = []
    for idx, segment in enumerate(text_segments, start=1):
        result = text_to_speech(
            text=segment,
            voice_id=voice_id,
        )
        result["segment_index"] = idx
        results.append(result)
    return results


# ============================================================================
# 模块二：视觉分发路由（黄金 30 秒死守策略）
# ============================================================================

def video_generation_api(
    prompt: str,
    duration_seconds: float,
    resolution: str = "1080p",
) -> dict:
    """
    视频生成 API 函数（Mock 实现）。
    用于生成短视频片段。适用于前 30 秒的高价值内容。

    参数：
      prompt           — 分镜画面提示词。
      duration_seconds — 该片段对应的时间戳（从脚本开始算起的秒数）。
      resolution       — 视频分辨率。

    返回：
      模拟的视频生成结果字典。
    """
    ensure_output_dirs()

    shot_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_shot_{shot_id}_{timestamp}.mp4"
    video_path = os.path.join(VISUAL_OUTPUT_DIR, filename)

    # 生成模拟视频文件
    with open(video_path, "w", encoding="utf-8") as f:
        f.write(f"# MOCK VIDEO FILE\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Prompt: {prompt}\n")
        f.write(f"# Duration: {duration_seconds}s | Resolution: {resolution}\n")

    return {
        "type": "video",
        "file_path": video_path,
        "prompt": prompt,
        "duration_seconds": duration_seconds,
        "resolution": resolution,
        "status": "mock",
    }


def image_generation_api(
    prompt: str,
    duration_seconds: float,
    resolution: str = "1080x1920",
) -> dict:
    """
    图像生成 API 函数（Mock 实现）。
    用于生成静态帧。适用于 30 秒后的辅助内容。

    参数：
      prompt           — 分镜画面提示词。
      duration_seconds — 该片段对应的时间戳（从脚本开始算起的秒数）。
      resolution       — 图片分辨率。

    返回：
      模拟的图像生成结果字典。
    """
    ensure_output_dirs()

    shot_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"image_shot_{shot_id}_{timestamp}.png"
    image_path = os.path.join(VISUAL_OUTPUT_DIR, filename)

    # 生成模拟图像文件
    with open(image_path, "w", encoding="utf-8") as f:
        f.write(f"# MOCK IMAGE FILE\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Prompt: {prompt}\n")
        f.write(f"# Duration: {duration_seconds}s | Resolution: {resolution}\n")

    return {
        "type": "image",
        "file_path": image_path,
        "prompt": prompt,
        "duration_seconds": duration_seconds,
        "resolution": resolution,
        "status": "mock",
    }


def visual_distribution_router(
    storyboard_shots: list,
) -> list:
    """
    视觉分发路由调度器 —— 黄金 30 秒死守策略。

    核心规则（不可绕过）：
      - 前 30 秒（duration_seconds <= 30）：强制路由到视频生成 API。
      - 30 秒之后（duration_seconds > 30）：强制路由到图像生成 API。

    为什么这么分：
      - 前 30 秒是短视频的黄金窗口，用户的留存率在此决定。
        动态视频比静态图片的留存率高 3~5 倍。
      - 30 秒后用户已经形成观看惯性，静态图片配合 TTS 配音即可
        维持注意力，成本仅为视频的 1/10。

    参数：
      storyboard_shots — 分镜列表，每项包含：
        - "prompt": 画面提示词（字符串）
        - "duration_seconds": 该分镜在脚本时间轴上的位置（秒）

    返回：
      每个分镜的生成结果字典列表，含 type 字段标记 "video" 或 "image"。
    """
    if not storyboard_shots:
        return []

    results = []
    video_count = 0
    image_count = 0

    for shot in storyboard_shots:
        prompt = shot.get("prompt", "")
        duration = shot.get("duration_seconds", 0)

        # ── 黄金 30 秒死守判断 ──
        if duration <= GOLDEN_30S_THRESHOLD:
            # 前 30 秒：强制视频
            result = video_generation_api(prompt=prompt, duration_seconds=duration)
            result["route_reason"] = f"黄金 30 秒内（{duration}s <= {GOLDEN_30S_THRESHOLD}s）→ 强制视频"
            video_count += 1
        else:
            # 30 秒后：强制图像
            result = image_generation_api(prompt=prompt, duration_seconds=duration)
            result["route_reason"] = f"30 秒后（{duration}s > {GOLDEN_30S_THRESHOLD}s）→ 强制图像"
            image_count += 1

        results.append(result)

    # 打印分发统计
    print(f"\n{'=' * 50}")
    print(f"  视觉分发路由报告")
    print(f"{'=' * 50}")
    print(f"  总分镜数: {len(storyboard_shots)}")
    print(f"  [VIDEO] 视频生成: {video_count} 个（前 {GOLDEN_30S_THRESHOLD}s 黄金窗口）")
    print(f"  [IMG] 图像生成: {image_count} 个（{GOLDEN_30S_THRESHOLD}s 之后）")
    print(f"{'=' * 50}\n")

    return results


# ============================================================================
# 模块三：人机协作拦截器（品控把关）
# ============================================================================

def human_review_interceptor(
    candidates: list,
    review_mode: str = "strict",
) -> list:
    """
    人机协作拦截器 —— 品控把关的最后一道防线。

    流程：
      1. 将视觉模型输出的所有候选素材逐条展示给人类审核员。
      2. 进入阻塞状态（input() 等待终端输入），
         必须等待人类逐条输入"确认采纳"或"驳回"。
      3. 只有被标记为"确认采纳"的素材才能通过，进入最终输出。
      4. 被驳回的素材记录驳回原因，供后续重生成使用。

    参数：
      candidates  — 视觉分发路由输出的候选素材列表。
      review_mode — "strict"（默认）：每一条都必须人工确认；
                    "batch"：批量确认，一次性 approve 全部。

    返回：
      通过审核的素材列表 + 驳回记录。
    """
    if not candidates:
        print("\n[WARN] 没有待审核的候选素材，跳过品控环节。")
        return []

    total = len(candidates)
    print(f"\n{'=' * 60}")
    print(f"  [REVIEW] 人机协作品控拦截器已启动")
    print(f"  待审核素材: {total} 条")
    print(f"  审核模式: {review_mode}")
    print(f"  请输入 '确认采纳' 通过，输入其他内容视为驳回")
    print(f"{'=' * 60}\n")

    approved = []
    rejected = []

    if review_mode == "batch":
        # 批量模式：一次性展示全部，一次性确认
        for idx, candidate in enumerate(candidates, start=1):
            print(f"  ┌─ [{idx}/{total}] {candidate.get('type', '?').upper()} ─┐")
            print(f"  │ Prompt: {candidate.get('prompt', 'N/A')[:80]}...")
            print(f"  │ 时间戳: {candidate.get('duration_seconds', '?')}s")
            print(f"  │ 路由原因: {candidate.get('route_reason', 'N/A')}")
            print(f"  └{'─' * 50}┘\n")

        decision = input(f"  请输入 '确认采纳' 批量通过全部 {total} 条素材: ").strip()

        if decision == "确认采纳":
            for c in candidates:
                c["review_status"] = "approved"
                approved.append(c)
            print(f"\n  [OK] 批量通过！{total} 条素材全部采纳。")
        else:
            for c in candidates:
                c["review_status"] = "rejected"
                c["reject_reason"] = f"批量驳回: 审核员输入了 '{decision}'"
                rejected.append(c)
            print(f"\n  [X] 批量驳回！{total} 条素材全部拒绝。驳回原因: {decision}")
    else:
        # 严格模式：逐条审核
        for idx, candidate in enumerate(candidates, start=1):
            print(f"  ┌─ [{idx}/{total}] {candidate.get('type', '?').upper()} ─┐")
            print(f"  │ Prompt: {candidate.get('prompt', 'N/A')[:80]}...")
            print(f"  │ 时间戳: {candidate.get('duration_seconds', '?')}s")
            print(f"  │ 路由原因: {candidate.get('route_reason', 'N/A')}")
            print(f"  │ 文件: {candidate.get('file_path', 'N/A')}")
            print(f"  └{'─' * 50}┘")

            # ── 阻塞等待人类输入 ──
            decision = input(f"  → 请输入审核决定（确认采纳 / 驳回+原因）: ").strip()

            if decision == "确认采纳":
                candidate["review_status"] = "approved"
                approved.append(candidate)
                print(f"     [OK] 已采纳\n")
            else:
                candidate["review_status"] = "rejected"
                candidate["reject_reason"] = decision
                rejected.append(candidate)
                print(f"     [X] 已驳回。原因: {decision}\n")

    # ── 品控报告 ──
    print(f"\n{'=' * 60}")
    print(f"  品控审核报告")
    print(f"{'=' * 60}")
    print(f"  通过: {len(approved)} / {total}")
    print(f"  驳回: {len(rejected)} / {total}")
    if rejected:
        print(f"  驳回列表:")
        for r in rejected:
            print(f"    - [{r.get('type')}] {r.get('reject_reason', 'N/A')}")
    print(f"{'=' * 60}\n")

    return approved, rejected


# ============================================================================
# 主流程编排
# ============================================================================

def run_phase3_pipeline(
    storyboard_shots: list,
    tts_segments: list = None,
    skip_human_review: bool = False,
) -> dict:
    """
    第三阶段完整流水线：TTS 配音 → 视觉分发路由 → 人机品控。

    参数：
      storyboard_shots  — 分镜列表，每项含 prompt 和 duration_seconds。
      tts_segments      — TTS 文本片段列表（可选）。
      skip_human_review — 是否跳过人机品控（仅用于自动化测试）。

    返回：
      完整的第三阶段输出字典。
    """
    print("\n" + "=" * 60)
    print("  启量 Agent — 第三阶段流水线启动")
    print(f"  启动时间: {datetime.now().isoformat()}")
    print("=" * 60)

    pipeline_result = {
        "pipeline": "phase3_multimodal",
        "timestamp": datetime.now().isoformat(),
        "tts": None,
        "visual": None,
        "review": None,
    }

    # ── 步骤 1：TTS 配音 ──
    if tts_segments:
        print("\n[TTS] 步骤 1/3: TTS 配音处理中...")
        tts_results = batch_tts(tts_segments)
        pipeline_result["tts"] = {
            "total_segments": len(tts_segments),
            "total_duration_seconds": sum(r["duration_seconds"] for r in tts_results),
            "segments": tts_results,
        }
        print(f"   完成: {len(tts_results)} 段配音，"
              f"预估总时长 {pipeline_result['tts']['total_duration_seconds']}s")
    else:
        print("\n[TTS] 步骤 1/3: 无 TTS 文本，跳过配音环节。")

    # ── 步骤 2：视觉分发路由 ──
    print("\n[VIDEO] 步骤 2/3: 视觉分发路由中...")
    visual_results = visual_distribution_router(storyboard_shots)
    pipeline_result["visual"] = {
        "total_shots": len(storyboard_shots),
        "results": visual_results,
    }

    # ── 步骤 3：人机品控 ──
    if skip_human_review:
        print("\n[REVIEW] 步骤 3/3: 人机品控已跳过（自动化模式）。")
        pipeline_result["review"] = {
            "mode": "skipped",
            "approved": visual_results,
            "rejected": [],
        }
    else:
        print("\n[REVIEW] 步骤 3/3: 进入人机品控环节...")
        approved, rejected = human_review_interceptor(visual_results)
        pipeline_result["review"] = {
            "mode": "manual",
            "approved": approved,
            "rejected": rejected,
            "approval_rate": f"{len(approved)}/{len(visual_results)}",
        }

    print("\n[OK] 第三阶段流水线执行完毕。")
    return pipeline_result


# ============================================================================
# 独立测试入口
# ============================================================================

if __name__ == "__main__":
    # ── 模拟 Phase 2 分镜输出的测试数据 ──
    mock_storyboard_shots = [
        {
            "prompt": "Close-up shot, a glossy red apple with anthropomorphic smiling face, "
                      "studio lighting with soft shadows, vibrant colors, 3D animated style --ar 16:9",
            "duration_seconds": 5,  # 前 30 秒 → 应路由到视频
        },
        {
            "prompt": "Medium shot, supermarket aisle with colorful fruit shelves, "
                      "bright overhead LED lights, clean modern aesthetic, 3D animated style --ar 16:9",
            "duration_seconds": 12,  # 前 30 秒 → 应路由到视频
        },
        {
            "prompt": "Close-up on a mysterious spray bottle emerging from mist, "
                      "dramatic spotlight, slow camera pan, cinematic depth of field --ar 16:9",
            "duration_seconds": 22,  # 前 30 秒 → 应路由到视频
        },
        {
            "prompt": "Wide shot, before-and-after split screen: dull apple on left, "
                      "shiny glowing apple on right, comparison format --ar 16:9",
            "duration_seconds": 35,  # 30 秒后 → 应路由到图像
        },
        {
            "prompt": "Product beauty shot, the保鲜喷雾 bottle on a white pedestal, "
                      "water droplets, premium product photography style --ar 16:9",
            "duration_seconds": 48,  # 30 秒后 → 应路由到图像
        },
    ]

    # ── 模拟 TTS 文本片段 ──
    mock_tts_segments = [
        "你有没有想过，为什么超市里的苹果永远那么亮？",
        "其实背后藏着一个不为人知的保鲜黑科技！",
        "这款保鲜喷雾，喷一下就能让水果发光7天！",
        "限时特惠，前100名下单立减50元！",
    ]

    print("\n" + "=" * 60)
    print("  启量 Agent — 第三阶段 多模态视觉铸造与品控车间")
    print("  独立功能测试")
    print("=" * 60)

    # ── 测试 1：单独测 TTS ──
    print("\n【子测试 1】TTS 配音通道")
    print("-" * 40)
    tts_result = text_to_speech(mock_tts_segments[0])
    print(f"  音频路径: {tts_result['audio_path']}")
    print(f"  预估时长: {tts_result['duration_seconds']}s")
    print(f"  状态: {tts_result['status']}")

    # ── 测试 2：单独测视觉路由 ──
    print("\n【子测试 2】视觉分发路由（黄金 30 秒）")
    print("-" * 40)
    route_results = visual_distribution_router(mock_storyboard_shots)
    for r in route_results:
        print(f"  [{r['type'].upper()}] {r['duration_seconds']}s → {r['route_reason']}")

    # ── 测试 3：人机品控（自动化模式，跳过 input）──
    print("\n【子测试 3】人机品控（自动化跳过模式）")
    print("-" * 40)
    approved, rejected = human_review_interceptor(
        route_results,
        review_mode="strict",
    ) if False else (route_results, [])  # 跳过交互

    # ── 完整流水线（跳过品控）──
    print("\n【完整流水线】")
    print("-" * 40)
    full_result = run_phase3_pipeline(
        storyboard_shots=mock_storyboard_shots,
        tts_segments=mock_tts_segments,
        skip_human_review=True,  # 自动化测试跳过人机交互
    )

    # 打印摘要
    print("\n" + "=" * 60)
    print("  测试完成！输出目录结构:")
    print("=" * 60)
    for root, dirs, files in os.walk(OUTPUT_DIR):
        level = root.replace(OUTPUT_DIR, "").count(os.sep)
        indent = "  " * level
        print(f"{indent}{os.path.basename(root)}/")
        sub_indent = "  " * (level + 1)
        for file in files:
            print(f"{sub_indent}{file}")

    print(f"\n总输出文件数: {sum(len(files) for _, _, files in os.walk(OUTPUT_DIR))}")
