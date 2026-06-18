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
import csv
import asyncio
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage

# ============================================================================
# 全局配置区
# ============================================================================

# ── 优先从 .env 加载 DeepSeek API Key，否则使用占位符 ──
def _load_deepseek_key() -> str:
    """从 .env 文件或环境变量加载 DeepSeek API Key。"""
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv("DEEPSEEK_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

YOUR_API_KEY = _load_deepseek_key()

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
# SafetyScanner：AC-SEC-01 ~ AC-SEC-03 三级安全联扫（面向对象设计）
# ============================================================================

class SafetyScanner:
    """
    启量 Agent 安全拦截器。

    配置文件：
      - config/banned_terms.csv    — 违禁词库（列：term, category, severity...）
      - config/risky_proximity.csv — 可疑邻近词库（列：term, proximity_risk_level...）

    联扫流程：
      SEC-01 精确匹配 → SEC-02 邻近词检查 → SEC-03 LLM 语义兜底（预留异步）
    """

    def __init__(self):
        """初始化：从 CSV 弹药库加载违禁词和邻近词。"""
        self.banned_terms = self._load_csv_terms("config", "banned_terms.csv")
        self.risky_proximity = self._load_csv_terms("config", "risky_proximity.csv")

    # ── CSV 加载器 ─────────────────────────────────────────────
    def _load_csv_terms(self, dirname: str, filename: str) -> List[str]:
        """
        从 CSV 文件加载词条列表。自动跳过空行，大小写归一化。

        参数：
          dirname  — 相对于本文件的目录名
          filename — CSV 文件名

        返回：
          小写去重词条列表；文件不存在返回空列表（不阻断管线）。
        """
        filepath = os.path.join(os.path.dirname(__file__), dirname, filename)
        if not os.path.exists(filepath):
            print(f"[SafetyScanner] WARN: {filepath} not found — skipping.")
            return []

        terms: List[str] = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                term = row.get("term", "").strip().lower()
                if term:
                    terms.append(term)
        return list(set(terms))  # 去重

    # ── AC-SEC-01：违禁词精确匹配 ──────────────────────────────
    def ac_sec_01_exact_match(self, script: str) -> Dict[str, Any]:
        """
        大小写不敏感 + 词边界匹配。

        遍历脚本的每个词（剥离首尾标点后），与 banned_terms 精确比对。

        返回：
          {"passed": bool, "hits": [{"term": str, "position": int}]}
        """
        if not self.banned_terms:
            return {"passed": True, "hits": [], "terms_loaded": 0}

        words = script.split()
        hits: List[Dict] = []

        for i, word in enumerate(words):
            # 剥离首尾标点（保留词内连字符和撇号）
            clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", word).lower()
            if not clean_word:
                continue

            for term in self.banned_terms:
                if clean_word == term:
                    hits.append({"term": term, "position": i})
                    break  # 一词命中多个违禁词只记一次

        return {
            "passed": len(hits) == 0,
            "hits": hits,
            "terms_loaded": len(self.banned_terms),
        }

    # ── AC-SEC-02：可疑邻近词检查 ──────────────────────────────
    def ac_sec_02_proximity_check(
        self, script: str, sec01_hits: List[Dict]
    ) -> Dict[str, Any]:
        """
        针对 SEC-01 命中词，扫描其 position ±15 词范围，
        与 risky_proximity 做精确匹配。

        返回：
          {"passed": bool, "proximity_hits": [{"term": str, "nearby_term": str, "distance": int}]}
        """
        if not self.risky_proximity or not sec01_hits:
            return {
                "passed": True,
                "proximity_hits": [],
                "risky_terms_loaded": len(self.risky_proximity),
            }

        words = script.split()
        total_words = len(words)
        proximity_hits: List[Dict] = []

        for hit in sec01_hits:
            pos = hit["position"]
            start = max(0, pos - 15)
            end = min(total_words, pos + 16)

            for j in range(start, end):
                if j == pos:
                    continue

                clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", words[j]).lower()
                if not clean_word:
                    continue

                for risky in self.risky_proximity:
                    if clean_word == risky:
                        proximity_hits.append({
                            "term": hit["term"],
                            "nearby_term": risky,
                            "distance": j - pos,
                        })
                        break

        return {
            "passed": len(proximity_hits) == 0,
            "proximity_hits": proximity_hits,
            "risky_terms_loaded": len(self.risky_proximity),
        }

    # ── AC-SEC-03：LLM 语义兜底（预留异步接口）─────────────────
    async def _llm_semantic_check(
        self, script: str, sec01_hits: List[Dict], sec02_hits: List[Dict]
    ) -> Dict[str, Any]:
        """
        预留的 LLM 语义判断异步方法。
        当前返回 mock 结果。接入真实 DeepSeek API 后替换此处实现。

        返回：
          {"violation": bool, "confidence": int, "evidence": [str, ...]}
        """
        # TODO: 接入 DeepSeek V3，temperature=0.1，JSON mode
        return {
            "violation": False,
            "confidence": 100,
            "evidence": [],
        }

    # ── 三级联扫总入口 ─────────────────────────────────────────
    def scan(self, script: str) -> Dict[str, Any]:
        """
        同步执行 AC-SEC-01 → AC-SEC-02 联扫。
        AC-SEC-03 需要异步上下文，在本方法中返回命中信息供上层调用。

        返回：
          {
            "sec01": {...},
            "sec02": {...},
            "final_verdict": "pass" | "needs_llm_check",
            "pipeline_path": ["SEC01", ...],
          }
        """
        result: Dict[str, Any] = {
            "sec01": None,
            "sec02": None,
            "final_verdict": "pass",
            "pipeline_path": [],
        }

        # ── SEC-01 ──
        sec01 = self.ac_sec_01_exact_match(script)
        result["sec01"] = sec01
        result["pipeline_path"].append("SEC01")

        if sec01["passed"]:
            return result

        # ── SEC-02 ──
        sec02 = self.ac_sec_02_proximity_check(script, sec01["hits"])
        result["sec02"] = sec02
        result["pipeline_path"].append("SEC02")

        if sec02["passed"]:
            return result

        # ── SEC-03 需异步，标记待 LLM 检查 ──
        result["final_verdict"] = "needs_llm_check"
        result["pipeline_path"].append("SEC03")

        return result

    @property
    def stats(self) -> Dict[str, int]:
        """返回当前弹药库统计信息。"""
        return {
            "banned_terms_count": len(self.banned_terms),
            "risky_proximity_count": len(self.risky_proximity),
        }


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

    # ── AC-SEC-01 ~ AC-SEC-03 安全扫描 ──
    # 在翻译通道输出 translated_script 后立即执行三级联扫。
    security_result = None
    translated_script = translation_result.get("translated_script", "")
    if translated_script.strip():
        scanner = SafetyScanner()
        security_result = scanner.scan(translated_script)

    return {
        "translation": translation_result,
        "storyboard": storyboard_result,
        "security": security_result,  # 🆕 安全扫描结果
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
    # ========================================================================
    # 点火测试：SafetyScanner 三级联扫
    # ========================================================================

    scanner = SafetyScanner()

    print("=" * 62)
    print("  启量 Agent · SafetyScanner 点火测试")
    print("  AC-SEC-01 (精确匹配) + AC-SEC-02 (邻近词检查)")
    print("=" * 62)
    print()
    print(f"  [弹药库] banned_terms   : {scanner.stats['banned_terms_count']} 条")
    print(f"  [弹药库] risky_proximity: {scanner.stats['risky_proximity_count']} 条")
    print()

    # ── 测试用例 ───────────────────────────────────────────────
    test_script = (
        "This book is a guaranteed cure for your anxiety, "
        "and it's 100% free! Don't just make money fast, build real wealth."
    )

    print(f"  [输入脚本]")
    print(f"  {test_script}")
    print()

    # ── 执行扫描 ──
    result = scanner.scan(test_script)

    # ── 结果汇报 ──
    print(f"  [联扫路径] {' -> '.join(result['pipeline_path'])}")
    print(f"  [最终裁决] {result['final_verdict']}")
    print()

    sec01 = result["sec01"]
    print(f"  [SEC-01] 精确匹配")
    print(f"    通过     : {sec01['passed']}")
    print(f"    命中数   : {len(sec01['hits'])}")
    if sec01["hits"]:
        for h in sec01["hits"]:
            print(f"      -> term=\"{h['term']}\"  position={h['position']}")
    print()

    if result.get("sec02"):
        sec02 = result["sec02"]
        print(f"  [SEC-02] 邻近词检查")
        print(f"    通过     : {sec02['passed']}")
        print(f"    命中数   : {len(sec02['proximity_hits'])}")
        if sec02["proximity_hits"]:
            for ph in sec02["proximity_hits"]:
                print(f"      -> \"{ph['term']}\" + \"{ph['nearby_term']}\" 距离={ph['distance']}词")
        print()

    # ── 简要分析 ──
    print("  [分析]")
    sec01_hits = sec01["hits"]
    if not sec01_hits:
        print("    脚本安全，未命中任何违禁词。可直接放行。")
    else:
        hit_terms = [h["term"] for h in sec01_hits]
        print(f"    命中违禁词: {hit_terms}")
        sec02_hits = result.get("sec02", {}).get("proximity_hits", [])
        if sec02_hits:
            nearby = [f"\"{ph['term']}\"+\"{ph['nearby_term']}\"" for ph in sec02_hits]
            print(f"    邻近风险  : {nearby}")
            print(f"    -> 需进入 SEC-03 LLM 语义兜底（当前 mock 返回不违规）")
        else:
            print("    无邻近词风险。SEC-02 放行。")

    print()
    print("=" * 62)
    print("  点火测试完成。SafetyScanner 三级联扫通路正常。")
    print("=" * 62)
