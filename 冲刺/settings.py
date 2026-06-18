# 引入库
TORTOISE_ORM = {
    'connections': {
        'default': {
            #'engine': 'tortoise.backends.Asyncpg',  # PostgreSQL
            'engine': 'tortoise.backends.mysql',    # MySQL or MariaDB
            'credentials': {
                'host': '127.0.0.1',
                'port': '3306',
                'user': 'root',
                'password': '123456',
                'database': 'fastapi',
                'minsize': 1,
                'maxsize': 5,
                "echo": True
            }
        }
    },
    'apps': {
        'models': {
            'models': ['models', 'aerich.models'],
            'default_connection': 'default'
        }
    },
    'use_tz': False,
    'timezone': 'Asia/Shanghai'
}
# ── 数据模型注册 ──
# 模型文件：冲刺/models.py
# 核心表：BookUnderstanding / ExpressionTemplate / GeneratedScript
# 迁移工具：aerich (pip install aerich aiomysql)
#
# 首次迁移步骤：
#   cd 冲刺
#   aerich init -t settings.TORTOISE_ORM
#   aerich init-db
#   aerich migrate && aerich upgrade
# ──────────────────────────────────────────