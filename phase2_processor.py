"""
================================================================================
 启量 Agent — 第二阶段：非结构化文字与视频处理
 异步并发处理模块（独立于 app.py，完全解耦）
 技术栈：asyncio 并发引擎 + LangChain (ainvoke) + DeepSeek API
================================================================================

 【设计原则】
  - 不修改 app.py，本模块作为独立的下游消费者。
  - 翻译通道和分镜通道通过 asyncio.gather 并行执行。
  - 两个通道的提示词从外部 txt 文件加载（物理隔离）。
  - 支持语种参数化（target_language），方便后续扩展多语言。
================================================================================
"""

import re
import json
import os
import asyncio
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

# 大模型温度参数：第二阶段任务需要比第一阶段稍高的灵活度
# 翻译需要自然度，分镜需要创意，所以设 0.3（第一阶段是 0.1）
TEMPERATURE = 0.3

# 默认目标语言
DEFAULT_TARGET_LANGUAGE = "en"


# ============================================================================
# 提示词加载器（物理隔离机制，与 app.py 的设计语言保持一致）
# ============================================================================

def load_prompt_file(filename: str) -> str:
    """
    从外部 txt 文件加载提示词。
    文件与 phase2_processor.py 放在同一个目录下。

    参数：
      filename — 提示词文件名（例如 "prompt_translation.txt"）

    返回：
      文件内容字符串；如果文件不存在则抛出 FileNotFoundError。
    """
    prompt_file = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(
            f"提示词文件 {filename} 不存在！"
            f"请确保该文件位于 {os.path.dirname(__file__)} 目录下。"
        )
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================================
# 通道一：翻译处理（Translation Channel）
# ============================================================================

def build_translation_chain(api_key: str, target_language: str):
    """
    构建翻译通道的 LangChain 链。
    系统提示词从 prompt_translation.txt 加载。
    """
    system_prompt = load_prompt_file("prompt_translation.txt")

    # 人类消息模板 —— 告诉模型要翻什么、翻成什么语言
    human_template = """\
【目标语言代码】：{target_language}
【带货金句（原文）】：
{pitches_json}
【剧本文本（原文）】：
{script}

请按照系统提示中的 JSON 格式输出翻译结果。"""

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    # SystemMessage 避免大括号冲突；HumanMessage 模板保留变量替换
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessagePromptTemplate.from_template(human_template),
    ])

    return prompt | llm


async def run_translation(
    phase1_json: dict,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    api_key: str = YOUR_API_KEY,
) -> dict:
    """
    异步执行翻译通道：将带货金句和剧本文本翻译成目标语言。
    本函数独立运行，不依赖分镜通道的任何结果。
    """
    # 从 Phase 1 JSON 中提取需要翻译的内容
    product_pitches = phase1_json.get("product_pitch", [])
    script = phase1_json.get("script", "")

    # 如果没有任何可翻译的内容，直接返回空结果
    if not product_pitches and not script.strip():
        return {
            "translated_pitches": [],
            "translated_script": "",
            "localization_notes": [],
            "target_language": target_language,
            "status": "skipped",
        }

    chain = build_translation_chain(api_key, target_language)

    try:
        # 用 ainvoke 异步调用大模型（不阻塞事件循环）
        response = await chain.ainvoke({
            "target_language": target_language,
            "pitches_json": json.dumps(product_pitches, ensure_ascii=False),
            "script": script,
        })
        raw_output = response.content.strip()
        result = json.loads(raw_output)
        result["status"] = "ok"
        return result

    except json.JSONDecodeError:
        # JSON 解析失败兜底 —— 尝试正则提取
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                result["status"] = "ok"
                return result
            except json.JSONDecodeError:
                pass
        return _empty_translation_result(target_language, "json_parse_error")

    except Exception as e:
        return _empty_translation_result(target_language, f"error: {str(e)}")


def _empty_translation_result(target_language: str, status: str) -> dict:
    """返回一个结构一致的空翻译结果（异常兜底）。"""
    return {
        "translated_pitches": [],
        "translated_script": "",
        "localization_notes": [],
        "target_language": target_language,
        "status": status,
    }


# ============================================================================
# 通道二：分镜处理（Storyboard Channel）
# ============================================================================

def build_storyboard_chain(api_key: str):
    """
    构建分镜通道的 LangChain 链。
    系统提示词从 prompt_storyboard.txt 加载。
    """
    system_prompt = load_prompt_file("prompt_storyboard.txt")

    # 人类消息模板 —— 把 hook_sentences、visual_constraints、IP 风格全喂进去
    human_template = """\
【Hook 引子 / 冲突句】：
{hooks_json}
【画面硬性约束（visual_constraints）】：
{constraints_json}
【整体视觉基调（Target IP Style）】：
{target_ip_style}

请按照系统提示中的 JSON 格式为每一句 Hook 生成分镜提示词。"""

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessagePromptTemplate.from_template(human_template),
    ])

    return prompt | llm


async def run_storyboard(
    phase1_json: dict,
    api_key: str = YOUR_API_KEY,
) -> dict:
    """
    异步执行分镜通道：为每一个 Hook 句子生成精准的画面分镜提示词。
    本函数独立运行，不依赖翻译通道的任何结果。
    """
    hooks = phase1_json.get("hook_sentences", [])
    constraints = phase1_json.get("visual_constraints", [])
    ip_style = phase1_json.get("target_ip_style", "")

    # 如果没有 Hook 句子，分镜无从谈起
    if not hooks:
        return {
            "storyboard_prompts": [],
            "global_style_note": "",
            "shot_count": 0,
            "status": "skipped",
        }

    chain = build_storyboard_chain(api_key)

    try:
        response = await chain.ainvoke({
            "hooks_json": json.dumps(hooks, ensure_ascii=False),
            "constraints_json": json.dumps(constraints, ensure_ascii=False),
            "target_ip_style": ip_style,
        })
        raw_output = response.content.strip()
        result = json.loads(raw_output)
        result["status"] = "ok"
        return result

    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                result["status"] = "ok"
                return result
            except json.JSONDecodeError:
                pass
        return _empty_storyboard_result("json_parse_error")

    except Exception as e:
        return _empty_storyboard_result(f"error: {str(e)}")


def _empty_storyboard_result(status: str) -> dict:
    """返回一个结构一致的空分镜结果（异常兜底）。"""
    return {
        "storyboard_prompts": [],
        "global_style_note": "",
        "shot_count": 0,
        "status": status,
    }


# ============================================================================
# 并行调度引擎（核心入口）
# ============================================================================

async def process_phase2(
    phase1_json: dict,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    api_key: str = YOUR_API_KEY,
) -> dict:
    """
    第二阶段主入口：异步并行执行翻译和分镜两个通道。

    架构图：
      phase1_json (来自 app.py 的输出)
              │
      ┌───────┴────────┐
      ▼                ▼
   翻译通道         分镜通道
   (run_translation) (run_storyboard)
      │                │
      ▼                ▼
      └───────┬────────┘
              ▼
        合并结果输出

    参数：
      phase1_json — 第一阶段输出的字典，包含 hook_sentences、visual_constraints、
                     product_pitch、script、target_ip_style 等字段。
      target_language — 翻译目标语言代码，默认 "en"（英文）。
      api_key — DeepSeek API Key。

    返回：
      包含 translation 和 storyboard 两个键的字典，各自是独立通道的输出。
      如果某个通道失败，其值会包含 status 字段标记错误原因，
      不影响另一个通道的正常输出。
    """
    # asyncio.gather 同时启动两个协程，并发执行。
    # return_exceptions=True 确保一个通道炸了不会拖垮另一个。
    translation_task = run_translation(phase1_json, target_language, api_key)
    storyboard_task = run_storyboard(phase1_json, api_key)

    translation_result, storyboard_result = await asyncio.gather(
        translation_task,
        storyboard_task,
        return_exceptions=True,
    )

    # 如果某个通道抛出了未捕获异常，包装为错误字典
    if isinstance(translation_result, Exception):
        translation_result = _empty_translation_result(
            target_language, f"channel_crashed: {str(translation_result)}"
        )
    if isinstance(storyboard_result, Exception):
        storyboard_result = _empty_storyboard_result(
            f"channel_crashed: {str(storyboard_result)}"
        )

    return {
        "translation": translation_result,
        "storyboard": storyboard_result,
    }


# ============================================================================
# 同步包装器（供 Streamlit 等同步框架调用）
# ============================================================================

def process_phase2_sync(
    phase1_json: dict,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    api_key: str = YOUR_API_KEY,
) -> dict:
    """
    同步版本的 process_phase2。
    供 Streamlit 等不支持直接 await 的同步框架调用。
    内部用 asyncio.run 启动异步引擎。
    """
    return asyncio.run(process_phase2(phase1_json, target_language, api_key))


# ============================================================================
# 独立测试入口（python phase2_processor.py 直接运行）
# ============================================================================

if __name__ == "__main__":
    # 模拟第一阶段输出的 JSON 数据
    mock_phase1_output = {
        "hook_sentences": [
            "你有没有想过，为什么超市里的苹果永远那么亮？",
            "其实背后藏着一个不为人知的保鲜黑科技！",
        ],
        "visual_constraints": [
            "超市货架场景",
            "明亮柔和的顶光",
            "3D渲染风格",
        ],
        "product_pitch": [
            "这款保鲜喷雾，喷一下就能让水果发光7天！",
            "限时特惠，前100名下单立减50元！",
        ],
        "script": "你有没有想过，为什么超市里的苹果永远那么亮？其实背后藏着一个不为人知的保鲜黑科技！这款保鲜喷雾，喷一下就能让水果发光7天...",
        "target_ip_style": "3D拟人化水果角色",
    }

    print("=" * 60)
    print("  启量 Agent — 第二阶段 异步并发处理器 独立测试")
    print("=" * 60)
    print()
    print("[提示] 请在下方填入你的 DeepSeek API Key")
    print("      或者修改本文件顶部的 YOUR_API_KEY 变量")
    print()

    api_key_input = input("API Key（留空使用默认值）: ").strip()
    if not api_key_input:
        api_key_input = YOUR_API_KEY

    if api_key_input == "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        print()
        print("❌ 错误：请先填入有效的 DeepSeek API Key！")
        print("   方式一：修改 phase2_processor.py 顶部的 YOUR_API_KEY")
        print("   方式二：运行时直接粘贴 Key")
        exit(1)

    print()
    print("🚀 正在并行启动翻译通道和分镜通道...")
    print(f"   目标语言: {DEFAULT_TARGET_LANGUAGE}")
    print()

    result = process_phase2_sync(mock_phase1_output, api_key=api_key_input)

    print("=" * 60)
    print("  📊 翻译通道结果")
    print("=" * 60)
    trans = result["translation"]
    print(f"  状态: {trans.get('status')}")
    print(f"  目标语言: {trans.get('target_language')}")
    print(f"  翻译后金句: {trans.get('translated_pitches')}")
    print(f"  本地化备注: {trans.get('localization_notes')}")
    print()

    print("=" * 60)
    print("  🎬 分镜通道结果")
    print("=" * 60)
    story = result["storyboard"]
    print(f"  状态: {story.get('status')}")
    print(f"  分镜数量: {story.get('shot_count')}")
    print(f"  全局风格备注: {story.get('global_style_note')}")
    print(f"  分镜提示词:")
    for i, prompt_text in enumerate(story.get("storyboard_prompts", []), start=1):
        print(f"    {i}. {prompt_text}")
    print()

    print("=" * 60)
    print("  测试完成！")
    print("=" * 60)
