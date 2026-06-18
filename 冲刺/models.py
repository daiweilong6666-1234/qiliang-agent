"""
================================================================================
 启量 Agent — 数据模型层（Tortoise ORM + MySQL）
 对应《启量Agent_工程框架设计.md》第五章：双 RAG 库架构
================================================================================

 【核心表】
  BookUnderstanding   — 「讲什么」深度理解库（静态资产，每书一次）
  ExpressionTemplate  — 「怎么讲」表达模式库（消耗品，三次即弃）
  GeneratedScript     — 每日生成的 TikTok 脚本流水记录

 【迁移命令】
  cd 冲刺
  aerich init -t settings.TORTOISE_ORM    # 首次初始化
  aerich init-db                          # 生成初始迁移
  aerich migrate                          # 创建迁移文件
  aerich upgrade                          # 执行迁移
================================================================================
"""

from tortoise import fields
from tortoise.models import Model


class BookUnderstanding(Model):
    """
    「讲什么」深度理解库 — 静态资产

    每本书只采一次，入库后永久复用。
    由真正读过该书的人（运营/PM/外聘书评人）手动填写入库。
    V1.0 入库管控：Git PR review SOP。V2.0：加密硬阀门。

    对应 PRD：工程框架设计 §5.2
    """

    # ── 主键与标识 ──
    book_id = fields.CharField(
        max_length=64, pk=True,
        description="书籍唯一标识，格式如 'atomic_habits_001'"
    )
    book_title = fields.CharField(
        max_length=255,
        description="书名，如 '原子习惯'"
    )
    author = fields.CharField(
        max_length=255,
        description="作者全名"
    )

    # ── 深度理解字段 ──
    one_liner = fields.CharField(
        max_length=512,
        description="一句话概括，50 字内。如：'习惯是靠身份认同投票投出来的'"
    )

    core_insights = fields.JSONField(
        default=list,
        description=(
            "核心观点/争议点数组。每项含：angle, original_quote, explanation, keywords[]。"
            "结构：[{\"angle\":\"...\", \"original_quote\":\"...\", \"explanation\":\"...\", \"keywords\":[...]}]"
        )
    )

    unsuitable_angles = fields.JSONField(
        default=list,
        description=(
            "负面清单：不适合讲的角度。明确告诉 LLM 不要往这个方向写。"
            "结构：[\"不要讲'每天进步1%一年37倍'\", ...]"
        )
    )

    target_audience = fields.JSONField(
        default=dict,
        description=(
            "目标受众画像。结构：{\"profile\":\"...\", \"pain_points\":[...], \"desire\":\"...\"}"
        )
    )

    time_sensitivity = fields.CharField(
        max_length=255, null=True,
        description="时效性标记，如为 null 表示无时效限制"
    )

    # ── 元数据 ──
    curated_by = fields.CharField(
        max_length=64,
        description="采集人标识（运营/PM/外聘书评人）"
    )
    version = fields.IntField(
        default=1,
        description="版本号，修改递增"
    )
    created_at = fields.DatetimeField(
        auto_now_add=True,
        description="入库时间"
    )
    updated_at = fields.DatetimeField(
        auto_now=True,
        description="最后修改时间"
    )

    class Meta:
        table = "book_understanding"
        ordering = ["-created_at"]

    def __repr__(self):
        return f"<BookUnderstanding book_id={self.book_id} title='{self.book_title}'>"


class ExpressionTemplate(Model):
    """
    「怎么讲」表达模式库 — 消耗品

    每条模板使用三次后自动标记 deprecated。
    V1.0：手动 tally 计数（Notion/Excel，每天 60 秒）。
    V2.0：usage_count 自动递增 + max_usage 触达自动废弃。

    对应 PRD：工程框架设计 §5.3
    """

    # ── 主键与来源 ──
    card_id = fields.CharField(
        max_length=64, pk=True,
        description="模板唯一标识，格式如 'script_001'"
    )
    source_url = fields.CharField(
        max_length=512, null=True,
        description="TikTok 爆款视频链接，用于溯源"
    )
    persona_label = fields.CharField(
        max_length=32, null=True,
        description="账号人设主标签（如 '治愈慢节奏' / '快节奏毒舌'）。账号间硬隔离，不可跨标签复用。"
    )

    # ── 模板内容 ──
    angle_title = fields.CharField(
        max_length=255,
        description="角度标题，如 '时间管理 × 职场焦虑'"
    )
    template = fields.TextField(
        description="模板全文，含 {痛点}/{原理} 等占位符"
    )

    # ── Metadata 标签（检索配对关键） ──
    rhythm = fields.CharField(
        max_length=16,
        description="节奏类型：快 / 中 / 慢"
    )
    hook_type = fields.CharField(
        max_length=64,
        description="钩子类型：悬念反转型 / 数字型 / 反常识型 / 身份标签型"
    )
    emotion = fields.CharField(
        max_length=32,
        description="情绪标签：悬疑 / 激情 / 温馨 / 科技 / 搞笑"
    )

    # ── 数据表现 ──
    avg_completion = fields.CharField(
        max_length=8, null=True,
        description="来源视频的平均完播率，如 '32%'"
    )
    click_rate = fields.CharField(
        max_length=8, null=True,
        description="来源视频的点击率，如 '8%'"
    )

    # ── 消耗控制 ──
    usage_count = fields.IntField(
        default=0,
        description="已被 Prompt 引用的次数"
    )
    max_usage = fields.IntField(
        default=3,
        description="最大复用次数，触达后标记 deprecated"
    )
    deprecated = fields.BooleanField(
        default=False,
        description="是否已被废弃（不再参与检索）"
    )

    # ── 关键词索引 ──
    keywords = fields.JSONField(
        default=list,
        description="关键词数组，用于检索匹配"
    )

    # ── 元数据 ──
    created_at = fields.DatetimeField(
        auto_now_add=True,
        description="入库时间"
    )
    updated_at = fields.DatetimeField(
        auto_now=True,
        description="最后修改时间"
    )

    class Meta:
        table = "expression_template"
        ordering = ["-created_at"]

    def __repr__(self):
        return (
            f"<ExpressionTemplate card_id={self.card_id} "
            f"rhythm='{self.rhythm}' usage={self.usage_count}/{self.max_usage} "
            f"deprecated={self.deprecated}>"
        )


class GeneratedScript(Model):
    """
    TikTok 脚本生成记录 — 流水线产物

    每条记录 = 一次完整的从「讲什么」→「怎么讲」→ LLM 生成 → 安全扫描的全链路产物。
    V1.0 每天 10-15 条，所有数据从第一天就用结构化 schema 存下来。

    对应 PRD：工程框架设计 §5 + AC-SEC-01~06
    """

    # ── 主键 ──
    id = fields.IntField(pk=True, generated=True)

    # ── 外键关联 ──
    book = fields.ForeignKeyField(
        "models.BookUnderstanding",
        related_name="scripts",
        on_delete=fields.CASCADE,
        description="关联的「讲什么」深度理解条目"
    )
    expression = fields.ForeignKeyField(
        "models.ExpressionTemplate",
        related_name="scripts",
        on_delete=fields.SET_NULL,
        null=True,
        description="关联的「怎么讲」表达模板"
    )

    # ── 脚本内容 ──
    original_script = fields.TextField(
        description="中文原始生成脚本（Phase 1 输出）"
    )
    translated_script = fields.TextField(
        null=True,
        description="英文翻译脚本（Phase 2 翻译通道输出）"
    )

    # ── 安全扫描结果 ──
    safety_scan_passed = fields.BooleanField(
        default=True,
        description="安全扫描是否通过"
    )
    safety_scan_path = fields.JSONField(
        default=list,
        description="联扫路径，如 ['SEC01', 'SEC02', 'SEC03']"
    )
    safety_violation_reason = fields.TextField(
        null=True,
        description="违规拦截原因。记录 SEC-01 命中词 / SEC-02 邻近词 / SEC-03 LLM 判断结果"
    )

    # ── 发布数据 ──
    tiktok_account_id = fields.CharField(
        max_length=64, null=True,
        description="发布的 TikTok 账号 ID"
    )
    published_at = fields.DatetimeField(
        null=True,
        description="发布时间"
    )
    tiktok_video_url = fields.CharField(
        max_length=512, null=True,
        description="发布后的视频链接"
    )

    # ── 数据表现（发布后回填） ──
    play_count = fields.BigIntField(
        default=0,
        description="播放量"
    )
    completion_rate = fields.CharField(
        max_length=8, null=True,
        description="完播率，如 '32%'"
    )
    like_count = fields.IntField(
        default=0,
        description="点赞数"
    )
    comment_count = fields.IntField(
        default=0,
        description="评论数"
    )
    order_count = fields.IntField(
        default=0,
        description="TikTok Shop 归因订单数"
    )

    # ── 状态机 ──
    STATUS_CHOICES = [
        ("draft", "草稿"),
        ("generated", "已生成"),
        ("safety_blocked", "违规拦截"),
        ("safety_passed", "安全通过"),
        ("assembled", "已装配"),
        ("published", "已发布"),
        ("manual_review", "人工审核中"),
    ]
    status = fields.CharField(
        max_length=32,
        default="draft",
        description="脚本状态"
    )

    # ── 元数据 ──
    created_at = fields.DatetimeField(
        auto_now_add=True,
        description="生成时间"
    )
    updated_at = fields.DatetimeField(
        auto_now=True,
        description="最后修改时间"
    )

    class Meta:
        table = "generated_script"
        ordering = ["-created_at"]

    def __repr__(self):
        return (
            f"<GeneratedScript id={self.id} status='{self.status}' "
            f"orders={self.order_count}>"
        )


# ============================================================================
# 旧模型（User 示例）已移除。如需保留请从 git history 恢复。
# ============================================================================
