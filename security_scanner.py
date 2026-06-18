"""
================================================================================
 启量 Agent — 安全拦截器 (Security Scanner)
 实现 AC-SEC-01 ~ AC-SEC-03 三级联扫验收标准
================================================================================

 【AC 映射】
  AC-SEC-01: 违禁词精确匹配（大小写不敏感 + 词边界）
  AC-SEC-02: 可疑邻近词检查（命中词 ±15 词范围）
  AC-SEC-03: LLM 语义判断（DeepSeek V3, temperature=0.1, JSON mode）

 【调用方式】
  from security_scanner import run_security_scan
  result = run_security_scan(translated_script, api_key)
  → result["final_verdict"] 为 "pass" | "needs_human_review"
================================================================================
"""

import re
import json
import os
import csv
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage

# ============================================================================
# 配置文件路径
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNED_TERMS_CSV = os.path.join(BASE_DIR, "config", "banned_terms.csv")
RISKY_PROXIMITY_CSV = os.path.join(BASE_DIR, "config", "risky_proximity.csv")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL_NAME = "deepseek-chat"


# ============================================================================
# CSV 加载器
# ============================================================================

def load_csv_terms(filepath: str, column: str = "term") -> List[str]:
    """
    从 CSV 文件加载词条列表，自动过滤空行和表头残留。

    参数：
      filepath  — CSV 文件路径
      column    — 要提取的列名

    返回：
      小写去重词条列表；文件不存在则返回空列表（不阻断管线）。
    """
    if not os.path.exists(filepath):
        print(f"[SEC-SCANNER] ⚠ 配置文件不存在: {filepath}，跳过该层。")
        return []

    terms = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            term = row.get(column, "").strip().lower()
            if term:
                terms.append(term)
    return list(set(terms))  # 去重


# ============================================================================
# AC-SEC-01：违禁词精确匹配
# ============================================================================

def ac_sec_01_exact_match(translated_script: str) -> Dict[str, Any]:
    """
    大小写不敏感精确匹配 + 词边界。

    遍历脚本的每个词（去除标点后），与 banned_terms.csv 精确比对。

    返回：
      {"passed": bool, "hits": [{"term": str, "position": int}]}
    """
    banned_terms = load_csv_terms(BANNED_TERMS_CSV, column="term")

    if not banned_terms:
        return {"passed": True, "hits": [], "terms_loaded": 0}

    words = translated_script.split()
    hits = []

    for i, word in enumerate(words):
        # 去除首尾标点（保留词内连字符和撇号）
        clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", word).lower()
        if not clean_word:
            continue

        for term in banned_terms:
            # 词边界精确匹配
            if clean_word == term:
                hits.append({"term": term, "position": i})
                break  # 一个词命中多个违禁词只记一次

    return {
        "passed": len(hits) == 0,
        "hits": hits,
        "terms_loaded": len(banned_terms),
    }


# ============================================================================
# AC-SEC-02：可疑邻近词检查
# ============================================================================

def ac_sec_02_proximity_check(
    translated_script: str,
    sec01_hits: List[Dict],
) -> Dict[str, Any]:
    """
    针对 AC-SEC-01 的命中词，扫描其 position ±15 个词的范围，
    与 risky_proximity.csv 做精确匹配。

    返回：
      {"passed": bool, "proximity_hits": [{"term": str, "nearby_term": str, "distance": int}]}
    """
    risky_terms = load_csv_terms(RISKY_PROXIMITY_CSV, column="term")

    if not risky_terms or not sec01_hits:
        return {"passed": True, "proximity_hits": [], "risky_terms_loaded": len(risky_terms)}

    words = translated_script.split()
    total_words = len(words)
    proximity_hits = []

    for hit in sec01_hits:
        pos = hit["position"]
        start = max(0, pos - 15)
        end = min(total_words, pos + 16)  # +16 因为 range end 是 exclusive

        for j in range(start, end):
            if j == pos:
                continue  # 跳过命中词自身

            clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", words[j]).lower()
            if not clean_word:
                continue

            for risky in risky_terms:
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
        "risky_terms_loaded": len(risky_terms),
    }


# ============================================================================
# AC-SEC-03：LLM 语义判断
# ============================================================================

def build_security_llm_chain(api_key: str):
    """构建 AC-SEC-03 的 LangChain 链（DeepSeek V3, temp=0.1, JSON mode）。"""
    system_prompt = """\
You are a TikTok content compliance expert. Your sole task: determine whether a given
English text violates TikTok Community Guidelines regarding hate speech, political
taboos, or religious discrimination.

CRITICAL RULES:
1. Judge the text IN CONTEXT. A word like "Muslim" used in an anti-discrimination
   or educational context is NOT a violation.
2. You MUST provide exactly 3 direct quotes from the original text as evidence.
3. Output ONLY valid JSON. No markdown, no explanation outside the JSON.

Output JSON schema:
{
  "violation": true or false,
  "confidence": integer from 0 to 100,
  "evidence": ["exact quote 1 from text", "exact quote 2 from text", "exact quote 3 from text"]
}
"""

    human_template = """\
【Original Text (translated_script)】:
{translated_script}

【Flagged Terms from AC-SEC-01 (banned_terms match)】:
{sec01_json}

【Flagged Proximity Terms from AC-SEC-02 (risky proximity match)】:
{sec02_json}

Judge whether this text violates TikTok Community Guidelines, considering CONTEXT.
A flagged word appearing in an anti-discrimination, educational, or neutral context
is NOT a violation.
"""

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        model=MODEL_NAME,
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessagePromptTemplate.from_template(human_template),
    ])

    return prompt | llm


def ac_sec_03_llm_judgment(
    translated_script: str,
    sec01_hits: List[Dict],
    sec02_hits: List[Dict],
    api_key: str,
) -> Dict[str, Any]:
    """
    调用 DeepSeek V3 对文本做上下文的违规语义判断。

    返回：
      {"violation": bool, "confidence": int, "evidence": [str, str, str]}
      异常时返回 violation=True, confidence=0（保守策略：存疑即拦截）。
    """
    chain = build_security_llm_chain(api_key)

    try:
        response = chain.invoke({
            "translated_script": translated_script,
            "sec01_json": json.dumps(sec01_hits, ensure_ascii=False),
            "sec02_json": json.dumps(sec02_hits, ensure_ascii=False),
        })
        raw_output = response.content.strip()

        # 清理可能的 markdown 代码块包裹
        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        result = json.loads(raw_output)
        return {
            "violation": bool(result.get("violation", True)),
            "confidence": int(result.get("confidence", 0)),
            "evidence": result.get("evidence", []),
        }

    except json.JSONDecodeError:
        # JSON 解析失败 → 尝试正则提取
        match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                return {
                    "violation": bool(result.get("violation", True)),
                    "confidence": int(result.get("confidence", 0)),
                    "evidence": result.get("evidence", []),
                }
            except json.JSONDecodeError:
                pass
        return _llm_fallback_result("json_parse_error")

    except Exception as e:
        return _llm_fallback_result(str(e))


def _llm_fallback_result(error: str) -> Dict[str, Any]:
    """LLM 异常时的保守兜底：标记为违规，置信度 0，强制进入人工审核 (AC-SEC-04)。"""
    return {
        "violation": True,
        "confidence": 0,
        "evidence": [f"LLM_ERROR_FALLBACK: {error}"],
        "error": error,
    }


# ============================================================================
# 三级联扫总入口
# ============================================================================

def run_security_scan(translated_script: str, api_key: str) -> Dict[str, Any]:
    """
    执行 AC-SEC-01 → AC-SEC-02 → AC-SEC-03 三级联扫。

    流程：
      SEC-01 命中？→ No → pass
              → Yes → SEC-02 命中？→ No → pass
                                   → Yes → SEC-03 LLM 判断 → needs_human_review

    参数：
      translated_script — Phase 2 翻译通道输出的全量英文脚本
      api_key           — DeepSeek API Key

    返回：
      {
        "sec01": {...},
        "sec02": {...},
        "sec03": {...},
        "final_verdict": "pass" | "needs_human_review",
        "pipeline_path": ["SEC01", "SEC02", "SEC03"],  # 经过了哪些层
      }
    """
    result = {
        "sec01": None,
        "sec02": None,
        "sec03": None,
        "final_verdict": "pass",
        "pipeline_path": [],
    }

    # ── AC-SEC-01 ──
    sec01 = ac_sec_01_exact_match(translated_script)
    result["sec01"] = sec01
    result["pipeline_path"].append("SEC01")

    if sec01["passed"]:
        result["final_verdict"] = "pass"
        return result

    # ── AC-SEC-02 ──
    sec02 = ac_sec_02_proximity_check(translated_script, sec01["hits"])
    result["sec02"] = sec02
    result["pipeline_path"].append("SEC02")

    if sec02["passed"]:
        result["final_verdict"] = "pass"
        return result

    # ── AC-SEC-03 ──
    sec03 = ac_sec_03_llm_judgment(
        translated_script, sec01["hits"], sec02["proximity_hits"], api_key
    )
    result["sec03"] = sec03
    result["pipeline_path"].append("SEC03")

    # 无论 LLM 判什么，都标记为需要人工审核 (AC-SEC-04)
    result["final_verdict"] = "needs_human_review"

    return result


# ============================================================================
# 简化的单词检查（供 Phase 1 或其他模块直接调用）
# ============================================================================

def quick_scan_script(script_text: str) -> Dict[str, Any]:
    """
    快速扫描一段文本中是否包含违禁词（仅 AC-SEC-01，不触发 LLM）。
    供 Pipeline 其他阶段做轻量预检。
    """
    return ac_sec_01_exact_match(script_text)


# ============================================================================
# 独立测试入口
# ============================================================================

if __name__ == "__main__":
    # 测试 1：完全干净的脚本
    safe_script = (
        "Atomic Habits teaches us that small changes lead to remarkable results. "
        "The key is to focus on identity rather than goals. "
        "Click the link below to get your copy today."
    )

    # 测试 2：含违禁词的脚本
    risky_script = (
        "The Muslim community is dangerous and should not be trusted. "
        "This book reveals the truth about their terrorist activities. "
        "Buy now to learn the shocking facts."
    )

    # 测试 3：含违禁词但上下文是反歧视论述的脚本
    ambiguous_script = (
        "Some people claim the Muslim community is dangerous, but that is a harmful "
        "stereotype. This book fights against Islamophobia and religious discrimination. "
        "Read it to understand why diversity makes us stronger."
    )

    print("=" * 60)
    print("  启量 Agent — 安全拦截器 独立测试")
    print("  AC-SEC-01 ~ AC-SEC-03 三级联扫")
    print("=" * 60)
    print()

    # 提示加载状态
    banned = load_csv_terms(BANNED_TERMS_CSV)
    risky = load_csv_terms(RISKY_PROXIMITY_CSV)
    print(f"[CONFIG] banned_terms.csv : {len(banned)} 条")
    print(f"[CONFIG] risky_proximity.csv : {len(risky)} 条")
    print()

    for label, script in [
        ("✅ 干净脚本", safe_script),
        ("❌ 含违禁词脚本", risky_script),
        ("⚠️  反歧视语境脚本", ambiguous_script),
    ]:
        print(f"--- {label} ---")
        print(f"  Script: {script[:80]}...")
        result = run_security_scan(script, api_key="sk-placeholder")
        print(f"  Pipeline: {' → '.join(result['pipeline_path'])}")
        print(f"  Verdict : {result['final_verdict']}")
        if result["sec01"]:
            print(f"  SEC01 hits: {result['sec01']['hits']}")
        if result["sec02"]:
            print(f"  SEC02 hits: {result['sec02']['proximity_hits']}")
        if result.get("sec03") and result["sec03"].get("evidence"):
            print(f"  SEC03 evidence: {result['sec03']['evidence'][:2]}...")
        print()
