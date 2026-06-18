#安装迁移模型 aerich
# aerich是一种ORM迁移工具，需要结合tortoise异步orm框架使用。安装aerich

# pip install aiomysql -i https://pypi.tuna.tsinghua.edu.cn/simple

# pip install aerich -i https://pypi.tuna.tsinghua.edu.cn/simple

# aerich init -t settings.TORTOISE_ORM

# aerich init-db

# aerich migrate  # 创建迁移

# aerich upgrade  # 真正迁移

# aerich downgrade  # 回退迁移