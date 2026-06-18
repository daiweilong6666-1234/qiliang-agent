"""
================================================================================
 启量 Agent — V1.0 数据雷达
 技术栈：Streamlit（前端） + Tortoise ORM（异步引擎） + SQLite（数据舱）
================================================================================
"""

import asyncio
import os
import sys

import streamlit as st

# ── 确保能从 冲刺/ 导入 models ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "冲刺"))

from tortoise import Tortoise


# ============================================================================
# 数据库配置（SQLite 物理文件）
# ============================================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite3")

TORTOISE_ORM = {
    "connections": {
        "default": f"sqlite:///{DB_PATH}",
    },
    "apps": {
        "models": {
            "models": ["models"],
            "default_connection": "default",
        }
    },
    "use_tz": False,
    "timezone": "Asia/Shanghai",
}


# ============================================================================
# 异步安全请求封装
# ============================================================================
async def _init_orm():
    """初始化 Tortoise ORM 连接（幂等）。"""
    try:
        await Tortoise.init(config=TORTOISE_ORM)
    except Exception:
        pass  # 已初始化则忽略


async def _fetch_all_books() -> list:
    """获取「讲什么」库全部数据。"""
    await _init_orm()
    from models import BookUnderstanding
    books = await BookUnderstanding.all().order_by("-created_at")
    return [
        {
            "book_id": b.book_id,
            "book_title": b.book_title,
            "author": b.author,
            "one_liner": b.one_liner,
            "core_insights": b.core_insights,
            "unsuitable_angles": b.unsuitable_angles,
            "target_audience": b.target_audience,
            "curated_by": b.curated_by,
            "version": b.version,
            "created_at": str(b.created_at) if b.created_at else None,
        }
        for b in books
    ]


async def _fetch_all_exprs() -> list:
    """获取「怎么讲」库全部数据。"""
    await _init_orm()
    from models import ExpressionTemplate
    exprs = await ExpressionTemplate.all().order_by("-created_at")
    return [
        {
            "card_id": e.card_id,
            "persona_label": e.persona_label,
            "angle_title": e.angle_title,
            "template": e.template,
            "rhythm": e.rhythm,
            "hook_type": e.hook_type,
            "emotion": e.emotion,
            "usage_count": e.usage_count,
            "max_usage": e.max_usage,
            "deprecated": e.deprecated,
            "avg_completion": e.avg_completion,
            "click_rate": e.click_rate,
            "keywords": e.keywords,
            "source_url": e.source_url,
            "created_at": str(e.created_at) if e.created_at else None,
        }
        for e in exprs
    ]


async def _fetch_counts() -> dict:
    """获取各表记录数。"""
    await _init_orm()
    from models import BookUnderstanding, ExpressionTemplate, GeneratedScript
    return {
        "books": await BookUnderstanding.all().count(),
        "exprs": await ExpressionTemplate.all().count(),
        "scripts": await GeneratedScript.all().count(),
    }


# ── 同步包装 ──
def fetch_all_books() -> list:
    return asyncio.run(_fetch_all_books())


def fetch_all_exprs() -> list:
    return asyncio.run(_fetch_all_exprs())


def fetch_counts() -> dict:
    return asyncio.run(_fetch_counts())


# ============================================================================
# Streamlit UI
# ============================================================================
st.set_page_config(
    page_title="启量 Agent · 数据雷达",
    page_icon="🎯",
    layout="wide",
)

st.title("启量 Agent · V1.0 数据雷达")
st.caption("底层数据舱可视化看板 — SQLite + Tortoise ORM")

# ── 顶部统计卡片 ──
counts = fetch_counts()
col1, col2, col3 = st.columns(3)
col1.metric("🎯 讲什么 (内容锚点)", counts["books"])
col2.metric("🎬 怎么讲 (表达模板)", counts["exprs"])
col3.metric("📝 生成脚本", counts["scripts"])

st.divider()

# ── 标签页 ──
tab_what, tab_how = st.tabs(["🎯 讲什么 (内容锚点)", "🎬 怎么讲 (表达模板)"])

# ============================
# Tab 1：「讲什么」
# ============================
with tab_what:
    books = fetch_all_books()

    if not books:
        st.warning("暂无数据。请先运行 `python 冲刺/seed_data.py` 注入种子数据。")
    else:
        for book in books:
            with st.container(border=True):
                st.subheader(f"📖 {book['book_title']} ({book['book_id']})")
                st.caption(f"作者：{book['author']}  |  采集人：{book['curated_by']}  |  版本：v{book['version']}")

                # 一句话概括
                st.markdown(f"> **一句话概括：** {book['one_liner']}")

                # 核心观点
                with st.expander(f"💡 核心观点（{len(book['core_insights'])} 条）", expanded=True):
                    for i, insight in enumerate(book["core_insights"], 1):
                        st.markdown(f"**{i}. {insight.get('angle', 'N/A')}**")
                        if insight.get("original_quote"):
                            st.caption(f"原文引用：_{insight['original_quote']}_")
                        if insight.get("explanation"):
                            st.caption(f"个人理解：{insight['explanation']}")
                        if insight.get("keywords"):
                            kw = " · ".join(insight["keywords"])
                            st.caption(f"关键词：{kw}")
                        st.divider()

                # 负面清单
                with st.expander(f"🚫 负面清单（{len(book['unsuitable_angles'])} 条）", expanded=True):
                    for angle in book["unsuitable_angles"]:
                        st.markdown(f"- ✗ {angle}")

                # 目标受众
                if book.get("target_audience"):
                    ta = book["target_audience"]
                    with st.expander("👤 目标受众", expanded=False):
                        st.markdown(f"**画像：** {ta.get('profile', 'N/A')}")
                        st.markdown(f"**痛点：** {', '.join(ta.get('pain_points', []))}")
                        st.markdown(f"**渴望：** {ta.get('desire', 'N/A')}")

            st.divider()

# ============================
# Tab 2：「怎么讲」
# ============================
with tab_how:
    exprs = fetch_all_exprs()

    if not exprs:
        st.warning("暂无数据。请先运行 `python 冲刺/seed_data.py` 注入种子数据。")
    else:
        for expr in exprs:
            status_icon = "🚫" if expr["deprecated"] else "✅"
            with st.container(border=True):
                col_left, col_right = st.columns([3, 1])

                with col_left:
                    st.subheader(f"{status_icon} {expr['angle_title']} ({expr['card_id']})")
                    st.caption(
                        f"人设：{expr['persona_label'] or '未指定'}  |  "
                        f"节奏：{expr['rhythm']}  |  "
                        f"钩子：{expr['hook_type']}  |  "
                        f"情绪：{expr['emotion']}"
                    )

                    with st.expander("📝 模板全文", expanded=False):
                        st.text(expr["template"])

                    if expr.get("keywords"):
                        kw = " · ".join(expr["keywords"])
                        st.caption(f"关键词：{kw}")

                with col_right:
                    # 消耗计数
                    used_pct = expr["usage_count"] / expr["max_usage"] * 100 if expr["max_usage"] else 0
                    st.metric(
                        "📊 使用计数",
                        f"{expr['usage_count']} / {expr['max_usage']}",
                        delta="已废弃" if expr["deprecated"] else "活跃",
                        delta_color="inverse" if expr["deprecated"] else "normal",
                    )
                    if expr.get("avg_completion"):
                        st.caption(f"完播率：{expr['avg_completion']}")
                    if expr.get("click_rate"):
                        st.caption(f"点击率：{expr['click_rate']}")

            st.divider()

# ── 页脚 ──
st.divider()
st.caption(f"数据源：{DB_PATH}")
