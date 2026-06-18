"""
================================================================================
 启量 Agent — MVP 冷启动种子数据注入
 使用 Tortoise ORM 向 db.sqlite3 注入「讲什么」+「怎么讲」测试语料。
================================================================================

 【执行方式】
  cd 冲刺
  python seed_data.py
================================================================================
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tortoise import Tortoise, run_async
from models import BookUnderstanding, ExpressionTemplate


# ── 数据库配置 ─────────────────────────────────────────────
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "db.sqlite3"
)

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


async def seed_book_understanding():
    """注入「讲什么」深度理解库 —— 《原子习惯》"""
    print("[seed] Injecting BookUnderstanding: Atomic Habits...")

    book = await BookUnderstanding.create(
        book_id="atomic_habits_001",
        book_title="原子习惯",
        author="James Clear",
        one_liner="习惯不是靠意志力坚持的，是靠身份认同投票投出来的",
        core_insights=[
            {
                "angle": "身份认同 > 目标设定",
                "original_quote": "Every action you take is a vote for the type of person you wish to become",
                "explanation": "不要跟自己说'我要每天跑步'，要说'我是一个跑步的人'——每一次行动都是为你想成为的人投票",
                "keywords": ["身份", "认同", "投票", "习惯养成"],
            },
            {
                "angle": "环境线索 > 意志力",
                "original_quote": "Environment is the invisible hand that shapes human behavior",
                "explanation": "每天早上喝完第一口水之后立刻穿上跑鞋——环境触发比意志力可靠一百倍",
                "keywords": ["环境", "线索", "触发", "行为设计"],
            },
            {
                "angle": "微小习惯的复利效应",
                "original_quote": "Habits are the compound interest of self-improvement",
                "explanation": "不是'每天进步1%一年37倍'的数学游戏——而是每天做一个俯卧撑比计划一套完美健身方案更有用",
                "keywords": ["微小", "复利", "坚持", "改善"],
            },
            {
                "angle": "习惯计分卡 —— 先看见，再改变",
                "original_quote": "The first step to changing bad habits is to be on the lookout for them",
                "explanation": "把每天的行为写下来，标注好坏——你不标注，你就不知道自己在做什么",
                "keywords": ["计分卡", "觉察", "记录", "改变"],
            },
        ],
        unsuitable_angles=[
            "不要讲'每天进步1%一年后你会强大37倍'——这不是书的核心观点，是选择性截取数学公式",
            "不要用恐惧驱动（'你再不改变就完了''同龄人已经甩开你了'）——与本书的积极基调冲突",
            "不要讲'21天养成一个好习惯'——本书明确反对固定时间框架的神话",
            "不要过度承诺（'读完这本书你的人生就改变了'）——书本身强调的是微小改进的系统，不是一夜奇迹",
        ],
        target_audience={
            "profile": "想养成好习惯但总是三分钟热度的人",
            "pain_points": [
                "每次下决心最后都不了了之",
                "对自己失望，觉得缺乏意志力",
                "试过很多方法（打卡、奖惩、21天挑战）都没用",
            ],
            "desire": "一个不需要消耗意志力就能持续下去的习惯系统",
        },
        time_sensitivity=None,
        curated_by="PM",
        version=1,
    )

    print(f"  [OK] BookUnderstanding created: {book.book_id} - {book.book_title}")
    return book


async def seed_expression_templates():
    """
    注入「怎么讲」表达模式库 —— 2 条 TikTok 爆款模板。

    模板 1：悬念反转型（快节奏）
    模板 2：痛点共鸣型（中节奏）
    """
    print("[seed] Injecting ExpressionTemplates...")
    templates = []

    # ── 模板 1：悬念反转型 ──────────────────────────────────
    t1 = await ExpressionTemplate.create(
        card_id="script_001",
        source_url="https://www.tiktok.com/@bookreview/video/placeholder_001",
        persona_label="快节奏毒舌",
        angle_title="时间管理 × 职场焦虑",
        template=(
            "你有没有想过，为什么你加班越多、工作越做不完？\n"
            "其实不是你的问题——是{痛点}在设计你的时间。\n"
            "这本书里有一个反常识的结论：{原理}\n"
            "我第一次读到的时候后背发凉。\n"
            "如果你不想再用加班证明自己很努力，\n"
            "点击下方链接，今天半价。"
        ),
        rhythm="快",
        hook_type="悬念反转型",
        emotion="悬疑",
        avg_completion="32%",
        click_rate="8%",
        usage_count=0,
        max_usage=3,
        deprecated=False,
        keywords=["时间管理", "加班", "效率", "职场", "焦虑"],
    )
    templates.append(t1)

    # ── 模板 2：痛点共鸣型 ──────────────────────────────────
    t2 = await ExpressionTemplate.create(
        card_id="script_002",
        source_url="https://www.tiktok.com/@bookreview/video/placeholder_002",
        persona_label="治愈慢节奏",
        angle_title="习惯养成 × 自我怀疑",
        template=(
            "你是不是也这样——\n"
            "每次下决心要改变，最后都不了了之。\n"
            "然后对自己说：我就是这种人，我改不了。\n"
            "但这本书的作者说了一个完全相反的结论：\n"
            "{原理}\n"
            "不是你不行。是你一直在用错误的方法。\n"
            "这本书不是教你怎么变更好——\n"
            "是教你怎么不再对自己失望。\n"
            "链接在主页，今天半价。"
        ),
        rhythm="中",
        hook_type="痛点共鸣型",
        emotion="温馨",
        avg_completion="28%",
        click_rate="6%",
        usage_count=0,
        max_usage=3,
        deprecated=False,
        keywords=["习惯", "改变", "自我怀疑", "成长", "共鸣"],
    )
    templates.append(t2)

    for t in templates:
        print(f"  [OK] ExpressionTemplate created: {t.card_id} - {t.angle_title} [{t.rhythm}]")

    return templates


async def seed():
    """主入口：初始化连接 → 注入数据 → 验证 → 关闭。"""
    print("=" * 56)
    print("  启量 Agent · MVP 种子数据注入")
    print("=" * 56)
    print()

    await Tortoise.init(config=TORTOISE_ORM)

    # ── 清空已有数据（幂等重跑） ──
    existing_books = await BookUnderstanding.all().count()
    existing_exprs = await ExpressionTemplate.all().count()
    if existing_books or existing_exprs:
        print(f"[seed] Clearing existing data: {existing_books} books, {existing_exprs} templates")
        await ExpressionTemplate.all().delete()
        await BookUnderstanding.all().delete()

    # ── 注入 ──
    await seed_book_understanding()
    await seed_expression_templates()

    # ── 验证 ──
    book_count = await BookUnderstanding.all().count()
    expr_count = await ExpressionTemplate.all().count()

    print()
    print("=" * 56)
    print(f"  Seed complete.")
    print(f"  BookUnderstanding  : {book_count} records")
    print(f"  ExpressionTemplate : {expr_count} records")
    print(f"  Total              : {book_count + expr_count} records")
    print("=" * 56)

    await Tortoise.close_connections()


if __name__ == "__main__":
    run_async(seed())
