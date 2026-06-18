"""
================================================================================
 启量 Agent — 数据库初始化脚本（SQLite）
 使用 Tortoise ORM + aiosqlite 在项目根目录生成 db.sqlite3 物理文件。
================================================================================

 【执行方式】
  cd 冲刺
  python init_db.py

 【注意】
  本脚本用于本地开发/测试。生产环境使用 settings.py 中的 MySQL 配置。
================================================================================
"""

import asyncio
import os
import sys

# 确保能从 冲刺/ 目录导入 models
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tortoise import Tortoise, run_async


# ── SQLite 配置（物理文件，非内存库）────────────────────────
# 数据库文件生成在项目根目录：jak/db.sqlite3
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
            "models": ["models"],  # 仅加载核心模型（aerich.models 需先 aerich init）
            "default_connection": "default",
        }
    },
    "use_tz": False,
    "timezone": "Asia/Shanghai",
}


async def init_database():
    """初始化 Tortoise ORM 并自动生成所有表。"""
    print(f"[init_db] 数据库路径: {DB_PATH}")
    print(f"[init_db] 连接方式: SQLite (物理文件)")

    # 初始化连接 + 自动建表
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas(safe=True)

    # 验证表已创建
    conn = Tortoise.get_connection("default")
    # 查询所有表名
    tables = await conn.execute_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'aerich'"
    )
    table_names = [row[0] for row in tables[1]]
    print(f"[init_db] 已创建表 ({len(table_names)}): {table_names}")

    # 验证物理文件
    if os.path.exists(DB_PATH):
        size_kb = os.path.getsize(DB_PATH) / 1024
        print(f"[init_db] [OK] db.sqlite3 created: {DB_PATH} ({size_kb:.1f} KB)")
    else:
        print(f"[init_db] [FAIL] File not found!")

    await Tortoise.close_connections()


if __name__ == "__main__":
    run_async(init_database())
    print("[init_db] 数据库初始化完成。")
