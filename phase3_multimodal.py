"""
================================================================================
 启量 Agent — 第三阶段：多模态视觉铸造与品控车间（实弹版）
 独立模块（与 Phase 1 / Phase 2 完全解耦）
 核心能力：TTS 配音（硅基流动）· 视觉分发路由 · 人机协作品控 · 生图生视频（海螺AI）
================================================================================

 【API 挂载】
  - TTS 语音合成：硅基流动 (SiliconFlow) CosyVoice2 → 输出真实 .mp3 音频
  - 图像生成：海螺AI (MiniMax) image-01 → 输出真实 .png 图片
  - 视频生成：海螺AI (MiniMax) video-01 → 输出真实 .mp4 视频
================================================================================
"""

import os
import time
import hashlib
import requests
from datetime import datetime

# ============================================================================
# .env 配置加载器（无外部依赖，手动解析）
# ============================================================================


def _load_env():
    """手动解析项目根目录下的 .env 文件，写入 os.environ。"""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val


_load_env()

# ============================================================================
# 全局配置
# ============================================================================

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output_assets")
AUDIO_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "audio")
VISUAL_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "visual")

# 黄金 30 秒分界线（秒）
GOLDEN_30S_THRESHOLD = 30

# ── 硅基流动 TTS 配置 ──
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_TTS_MODEL = os.environ.get("SILICONFLOW_TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")

# ── 海螺AI (MiniMax) 配置 ──
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")


# ============================================================================
# 辅助工具
# ============================================================================

def ensure_output_dirs():
    """确保所有输出目录存在。"""
    os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(VISUAL_OUTPUT_DIR, exist_ok=True)


def generate_id(prefix: str, seed: str) -> str:
    """生成短唯一 ID。"""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{h}"


# ============================================================================
# 模块一：TTS 配音通道（硅基流动 CosyVoice2 — 实弹版）
# ============================================================================

def text_to_speech(
    text: str,
    voice_id: str = "FunAudioLLM/CosyVoice2-0.5B:alex",
    speed: float = 1.0,
    audio_format: str = "mp3",
) -> dict:
    """
    TTS 文本转语音 —— 调用硅基流动 CosyVoice2 API 生成真实 .mp3 音频。

    参数：
      text         — 需要转为语音的英文文本（来自 Phase 2 翻译通道）。
      voice_id     — 硅基流动音色 ID，默认 alex（英语男声）。
      speed        — 语速倍率，1.0 为正常语速。
      audio_format — 输出音频格式，默认 "mp3"。

    返回：
      字典，包含 audio_path / duration_seconds / status 等字段。
    """
    ensure_output_dirs()

    if not SILICONFLOW_API_KEY or SILICONFLOW_API_KEY == "your_siliconflow_api_key_here":
        return _fallback_tts(text, voice_id, audio_format, "no_api_key")

    char_count = len(text)
    estimated_duration = round(char_count / 4.0, 2)

    # 生成文件名
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tts_{voice_id.split(':')[-1] if ':' in voice_id else voice_id}_{timestamp}_{text_hash}.{audio_format}"
    audio_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    try:
        # ── 调用硅基流动 Audio Speech API（OpenAI 兼容）──
        resp = requests.post(
            f"{SILICONFLOW_BASE_URL}/audio/speech",
            headers={
                "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": SILICONFLOW_TTS_MODEL,
                "input": text,
                "voice": voice_id,
                "response_format": audio_format,
                "speed": speed,
            },
            timeout=60,
        )

        if resp.status_code == 200 and resp.content:
            with open(audio_path, "wb") as f:
                f.write(resp.content)
            file_size = os.path.getsize(audio_path)
            return {
                "audio_path": audio_path,
                "duration_seconds": estimated_duration,
                "text_length": char_count,
                "voice_id": voice_id,
                "status": "live",
                "text": text,
                "file_size_bytes": file_size,
            }
        else:
            print(f"  [TTS WARN] API 返回 {resp.status_code}: {resp.text[:200]}")
            return _fallback_tts(text, voice_id, audio_format, f"api_error_{resp.status_code}")

    except requests.exceptions.Timeout:
        return _fallback_tts(text, voice_id, audio_format, "timeout")
    except Exception as e:
        print(f"  [TTS ERROR] {e}")
        return _fallback_tts(text, voice_id, audio_format, f"error: {str(e)[:50]}")


def _fallback_tts(text: str, voice_id: str, audio_format: str, status: str) -> dict:
    """TTS 降级方案：保存文本占位文件 + 返回估算数据。"""
    char_count = len(text)
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tts_fallback_{voice_id.split(':')[-1] if ':' in voice_id else voice_id}_{timestamp}_{text_hash}.txt"
    audio_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    with open(audio_path, "w", encoding="utf-8") as f:
        f.write("# TTS FALLBACK — API 调用未成功\n")
        f.write(f"# Status: {status}\n")
        f.write(f"# Voice: {voice_id}\n")
        f.write(f"# Text: {text}\n")

    return {
        "audio_path": audio_path,
        "duration_seconds": round(char_count / 4.0, 2),
        "text_length": char_count,
        "voice_id": voice_id,
        "status": status,
        "text": text,
        "file_size_bytes": os.path.getsize(audio_path),
    }


def batch_tts(text_segments: list, voice_id: str = "FunAudioLLM/CosyVoice2-0.5B:alex") -> list:
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
        result = text_to_speech(text=segment, voice_id=voice_id)
        result["segment_index"] = idx
        results.append(result)
    return results


# ============================================================================
# 模块二：视觉生成引擎（海螺AI MiniMax — 实弹版）
# ============================================================================

def _minimax_headers() -> dict:
    """构建海螺AI API 请求头。"""
    return {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }


def _download_file(url: str, save_path: str, timeout: int = 120) -> bool:
    """从 URL 下载文件到本地路径。"""
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return os.path.getsize(save_path) > 100
    except Exception as e:
        print(f"  [DOWNLOAD ERROR] {e}")
    return False


def image_generation_api(
    prompt: str,
    duration_seconds: float,
    resolution: str = "1080x1920",
) -> dict:
    """
    图像生成 API —— 调用海螺AI (MiniMax) image-01 模型生成真实图片。

    参数：
      prompt           — 分镜画面提示词（英文 Prompt）。
      duration_seconds — 该片段对应的时间戳。
      resolution       — 图片分辨率。

    返回：
      生成的图像结果字典，含本地文件路径。
    """
    ensure_output_dirs()

    if not MINIMAX_API_KEY or MINIMAX_API_KEY == "your_minimax_api_key_here":
        return _fallback_visual("image", prompt, duration_seconds, "no_api_key")

    shot_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"image_shot_{shot_id}_{timestamp}.png"
    image_path = os.path.join(VISUAL_OUTPUT_DIR, filename)

    try:
        # ── 调用海螺AI 图像生成 API ──
        resp = requests.post(
            f"{MINIMAX_BASE_URL}/image_generation",
            headers=_minimax_headers(),
            json={
                "model": "image-01",
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "n": 1,
                "response_format": "url",
            },
            timeout=120,
        )

        if resp.status_code == 200:
            data = resp.json()
            image_url = None
            if "data" in data and len(data["data"]) > 0:
                image_url = data["data"][0].get("url", "")
            elif "url" in data:
                image_url = data["url"]

            if image_url:
                if _download_file(image_url, image_path):
                    return {
                        "type": "image",
                        "file_path": image_path,
                        "prompt": prompt,
                        "duration_seconds": duration_seconds,
                        "resolution": resolution,
                        "status": "live",
                        "source_url": image_url,
                    }
                else:
                    return _fallback_visual("image", prompt, duration_seconds, "download_failed")

        print(f"  [IMG WARN] API 返回 {resp.status_code}: {resp.text[:200]}")
        return _fallback_visual("image", prompt, duration_seconds, f"api_error_{resp.status_code}")

    except requests.exceptions.Timeout:
        return _fallback_visual("image", prompt, duration_seconds, "timeout")
    except Exception as e:
        print(f"  [IMG ERROR] {e}")
        return _fallback_visual("image", prompt, duration_seconds, f"error: {str(e)[:50]}")


def video_generation_api(
    prompt: str,
    duration_seconds: float,
    resolution: str = "1080p",
) -> dict:
    """
    视频生成 API —— 调用海螺AI (MiniMax) video-01 模型生成真实短视频。

    ⚠ 视频生成是异步任务，需要提交后轮询等待。Demo 中超时 180s，
    超时后降级为图像生成。

    参数：
      prompt           — 分镜画面提示词。
      duration_seconds — 该片段对应的时间戳。
      resolution       — 视频分辨率。

    返回：
      生成的视频结果字典，含本地文件路径。
    """
    ensure_output_dirs()

    if not MINIMAX_API_KEY or MINIMAX_API_KEY == "your_minimax_api_key_here":
        return _fallback_visual("video", prompt, duration_seconds, "no_api_key")

    shot_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_shot_{shot_id}_{timestamp}.mp4"
    video_path = os.path.join(VISUAL_OUTPUT_DIR, filename)

    try:
        # ── 步骤 1：提交视频生成任务 ──
        submit_resp = requests.post(
            f"{MINIMAX_BASE_URL}/video_generation",
            headers=_minimax_headers(),
            json={
                "model": "video-01",
                "prompt": prompt,
                "duration": 5,
                "aspect_ratio": "16:9",
            },
            timeout=30,
        )

        if submit_resp.status_code != 200:
            print(f"  [VIDEO WARN] 提交失败 {submit_resp.status_code}: {submit_resp.text[:200]}")
            # 视频生成失败 → 降级为图像
            print("  [VIDEO] 降级为图像生成...")
            img_result = image_generation_api(prompt, duration_seconds)
            img_result["type"] = "video"
            img_result["route_reason"] = (
                f"视频 API 不可用 → 降级为图像 (原因: api_error_{submit_resp.status_code})"
            )
            return img_result

        task_data = submit_resp.json()
        task_id = task_data.get("id") or task_data.get("task_id", "")

        if not task_id:
            return _fallback_visual("video", prompt, duration_seconds, "no_task_id")

        # ── 步骤 2：轮询等待视频生成完成 ──
        max_wait = 180  # Demo 最大等待 3 分钟
        poll_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            query_resp = requests.get(
                f"{MINIMAX_BASE_URL}/video_generation/{task_id}",
                headers=_minimax_headers(),
                timeout=30,
            )

            if query_resp.status_code == 200:
                query_data = query_resp.json()
                status = query_data.get("status", "")

                if status == "completed" or status == "succeeded":
                    video_url = (
                        query_data.get("url")
                        or query_data.get("video_url")
                        or (query_data.get("data", {}) if isinstance(query_data.get("data"), str) else "")
                    )
                    if not video_url and "data" in query_data and isinstance(query_data["data"], dict):
                        video_url = query_data["data"].get("url", "")

                    if video_url and _download_file(video_url, video_path):
                        return {
                            "type": "video",
                            "file_path": video_path,
                            "prompt": prompt,
                            "duration_seconds": duration_seconds,
                            "resolution": resolution,
                            "status": "live",
                            "source_url": video_url,
                            "task_id": task_id,
                        }

                elif status == "failed" or status == "error":
                    print(f"  [VIDEO WARN] 任务失败: {query_data}")
                    break

            print(f"  [VIDEO] 轮询中... (已等待 {elapsed}s)")

        # 超时 → 降级为图像
        print(f"  [VIDEO] 等待超时 ({elapsed}s) → 降级为图像生成")
        img_result = image_generation_api(prompt, duration_seconds)
        img_result["type"] = "video"
        img_result["route_reason"] = f"视频生成超时 ({elapsed}s > {max_wait}s) → 降级为图像"
        return img_result

    except requests.exceptions.Timeout:
        return _fallback_visual("video", prompt, duration_seconds, "timeout")
    except Exception as e:
        print(f"  [VIDEO ERROR] {e}")
        return _fallback_visual("video", prompt, duration_seconds, f"error: {str(e)[:50]}")


def _fallback_visual(viz_type: str, prompt: str, duration_seconds: float,
                     status: str) -> dict:
    """视觉生成降级方案：保存 Prompt 占位文件。"""
    shot_id = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{viz_type}_fallback_{shot_id}_{timestamp}.txt"
    file_path = os.path.join(VISUAL_OUTPUT_DIR, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# {viz_type.upper()} FALLBACK — API 调用未成功\n")
        f.write(f"# Status: {status}\n")
        f.write(f"# Prompt: {prompt}\n")
        f.write(f"# Duration: {duration_seconds}s\n")

    return {
        "type": viz_type,
        "file_path": file_path,
        "prompt": prompt,
        "duration_seconds": duration_seconds,
        "status": status,
    }


# ============================================================================
# 模块三：视觉分发路由（黄金 30 秒死守策略）
# ============================================================================

def visual_distribution_router(storyboard_shots: list) -> list:
    """
    视觉分发路由调度器 —— 黄金 30 秒死守策略。

    核心规则（不可绕过）：
      - 前 30 秒（duration_seconds <= 30）：强制路由到视频生成 API。
      - 30 秒之后（duration_seconds > 30）：强制路由到图像生成 API。

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

        if duration <= GOLDEN_30S_THRESHOLD:
            result = video_generation_api(prompt=prompt, duration_seconds=duration)
            result["route_reason"] = (
                f"黄金 30 秒内（{duration}s <= {GOLDEN_30S_THRESHOLD}s）→ 强制视频"
            )
            video_count += 1
        else:
            result = image_generation_api(prompt=prompt, duration_seconds=duration)
            result["route_reason"] = (
                f"30 秒后（{duration}s > {GOLDEN_30S_THRESHOLD}s）→ 强制图像"
            )
            image_count += 1

        results.append(result)

    print(f"\n{'=' * 50}")
    print("  视觉分发路由报告")
    print(f"{'=' * 50}")
    print(f"  总分镜数: {len(storyboard_shots)}")
    print(f"  [VIDEO] 视频生成: {video_count} 个（前 {GOLDEN_30S_THRESHOLD}s 黄金窗口）")
    print(f"  [IMG] 图像生成: {image_count} 个（{GOLDEN_30S_THRESHOLD}s 之后）")
    print(f"{'=' * 50}\n")

    return results


# ============================================================================
# 模块四：人机协作拦截器（品控把关）
# ============================================================================

def human_review_interceptor(candidates: list, review_mode: str = "strict") -> list:
    """
    人机协作拦截器 —— 品控把关的最后一道防线。
    Streamlit 模式下不使用 terminal input()，此函数保留供命令行独立测试。
    """
    if not candidates:
        print("\n[WARN] 没有待审核的候选素材，跳过品控环节。")
        return []

    total = len(candidates)
    print(f"\n{'=' * 60}")
    print("  [REVIEW] 人机协作品控拦截器已启动")
    print(f"  待审核素材: {total} 条")
    print(f"  审核模式: {review_mode}")
    print("  请输入 '确认采纳' 通过，输入其他内容视为驳回")
    print(f"{'=' * 60}\n")

    approved = []
    rejected = []

    if review_mode == "batch":
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
        for idx, candidate in enumerate(candidates, start=1):
            print(f"  ┌─ [{idx}/{total}] {candidate.get('type', '?').upper()} ─┐")
            print(f"  │ Prompt: {candidate.get('prompt', 'N/A')[:80]}...")
            print(f"  │ 时间戳: {candidate.get('duration_seconds', '?')}s")
            print(f"  │ 路由原因: {candidate.get('route_reason', 'N/A')}")
            print(f"  │ 文件: {candidate.get('file_path', 'N/A')}")
            print(f"  └{'─' * 50}┘")
            decision = input("  → 请输入审核决定（确认采纳 / 驳回+原因）: ").strip()
            if decision == "确认采纳":
                candidate["review_status"] = "approved"
                approved.append(candidate)
                print("     [OK] 已采纳\n")
            else:
                candidate["review_status"] = "rejected"
                candidate["reject_reason"] = decision
                rejected.append(candidate)
                print(f"     [X] 已驳回。原因: {decision}\n")

    print(f"\n{'=' * 60}")
    print("  品控审核报告")
    print(f"{'=' * 60}")
    print(f"  通过: {len(approved)} / {total}")
    print(f"  驳回: {len(rejected)} / {total}")
    if rejected:
        print("  驳回列表:")
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
    print("  启量 Agent — 第三阶段流水线启动（实弹版）")
    print("  TTS: 硅基流动 CosyVoice2  |  生图/生视频: 海螺AI MiniMax")
    print(f"  启动时间: {datetime.now().isoformat()}")
    print("=" * 60)

    pipeline_result = {
        "pipeline": "phase3_multimodal_live",
        "timestamp": datetime.now().isoformat(),
        "tts": None,
        "visual": None,
        "review": None,
    }

    # ── 步骤 1：TTS 配音 ──
    if tts_segments:
        print("\n[TTS] 步骤 1/3: TTS 配音处理中（硅基流动 CosyVoice2）...")
        tts_results = batch_tts(tts_segments)
        pipeline_result["tts"] = {
            "total_segments": len(tts_segments),
            "total_duration_seconds": sum(r["duration_seconds"] for r in tts_results),
            "segments": tts_results,
        }
        live_count = sum(1 for r in tts_results if r.get("status") == "live")
        print(f"   完成: {len(tts_results)} 段配音, "
              f"其中 {live_count} 段为真实 API 生成, "
              f"预估总时长 {pipeline_result['tts']['total_duration_seconds']}s")
    else:
        print("\n[TTS] 步骤 1/3: 无 TTS 文本，跳过配音环节。")

    # ── 步骤 2：视觉分发路由 ──
    print("\n[VISUAL] 步骤 2/3: 视觉分发路由中（海螺AI MiniMax）...")
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
    mock_storyboard_shots = [
        {
            "prompt": "Close-up shot, a glossy red apple with anthropomorphic smiling face, "
                      "studio lighting with soft shadows, vibrant colors, 3D animated style --ar 16:9",
            "duration_seconds": 5,
        },
        {
            "prompt": "Medium shot, supermarket aisle with colorful fruit shelves, "
                      "bright overhead LED lights, clean modern aesthetic, 3D animated style --ar 16:9",
            "duration_seconds": 12,
        },
        {
            "prompt": "Close-up on a mysterious spray bottle emerging from mist, "
                      "dramatic spotlight, slow camera pan, cinematic depth of field --ar 16:9",
            "duration_seconds": 22,
        },
        {
            "prompt": "Wide shot, before-and-after split screen: dull apple on left, "
                      "shiny glowing apple on right, comparison format --ar 16:9",
            "duration_seconds": 35,
        },
    ]

    mock_tts_segments = [
        "Have you ever wondered why the apples in supermarkets always look so shiny?",
        "There is actually a hidden secret behind this freshness technology!",
        "This freshness spray can make your fruits glow for 7 days!",
    ]

    print("\n" + "=" * 60)
    print("  启量 Agent — 第三阶段 实弹版 功能测试")
    print("  TTS 引擎: 硅基流动 CosyVoice2")
    print("  视觉引擎: 海螺AI MiniMax")
    print("=" * 60)

    # ── 子测试 1：TTS ──
    print("\n【子测试 1】TTS 配音通道（硅基流动）")
    print("-" * 40)
    tts_result = text_to_speech(mock_tts_segments[0])
    print(f"  音频路径: {tts_result['audio_path']}")
    print(f"  预估时长: {tts_result['duration_seconds']}s")
    print(f"  状态: {tts_result['status']}")

    # ── 子测试 2：视觉路由 ──
    print("\n【子测试 2】视觉分发路由（海螺AI）")
    print("-" * 40)
    route_results = visual_distribution_router(mock_storyboard_shots)
    for r in route_results:
        print(f"  [{r.get('type', '?').upper()}] {r.get('duration_seconds', '?')}s → "
              f"{r.get('route_reason', 'N/A')} | status={r.get('status', '?')}")

    # ── 完整流水线 ──
    print("\n【完整流水线】")
    print("-" * 40)
    full_result = run_phase3_pipeline(
        storyboard_shots=mock_storyboard_shots,
        tts_segments=mock_tts_segments,
        skip_human_review=True,
    )

    print("\n" + "=" * 60)
    print("  测试完成！输出文件统计")
    print("=" * 60)
    for root, dirs, files in os.walk(OUTPUT_DIR):
        level = root.replace(OUTPUT_DIR, "").count(os.sep)
        indent = "  " * level
        print(f"{indent}{os.path.basename(root)}/")
        for file in files:
            file_path = os.path.join(root, file)
            size_kb = os.path.getsize(file_path) / 1024
            print(f"{indent}  {file} ({size_kb:.1f} KB)")
    print(f"\n总输出文件数: {sum(len(files) for _, _, files in os.walk(OUTPUT_DIR))}")
