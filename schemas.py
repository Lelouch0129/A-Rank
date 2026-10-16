# 规定 AI 必须返回什么格式

# ============================================================
# schemas.py
# 规定 AI 必须返回什么格式
# ============================================================

# ============================================================
# schemas.py
# A-Rank 所有结构化数据定义
# ============================================================

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================
# 1. Input Analysis / Clarification
# ============================================================

class DetectedItem(BaseModel):
    """
    AI 从用户输入中识别出的单个待估值对象。

    valuation_mode:
        market
        model
        entertainment

    experience_overlay:
        是否需要在真实市场价值之上，
        叠加体验价值 / 情境价值。

    例如：

        普通 iPhone
        -> market
        -> experience_overlay = False

        冰可乐的第一口
        -> market
        -> experience_overlay = True

        最后一张厕纸
        -> market
        -> experience_overlay = True

        高中三年的青春
        -> entertainment
        -> experience_overlay = False
    """

    id: str

    name: str

    valuation_mode: Literal[
        "market",
        "model",
        "entertainment"
    ]

    category: str

    known_information: list[str]

    experience_overlay: bool


class ClarificationQuestion(BaseModel):
    """
    针对某个具体 item 的追问。
    """

    id: str

    # 必须对应 DetectedItem.id
    item_id: str

    question: str

    placeholder: str

    reason: str


class AnalysisResult(BaseModel):
    """
    analyze_input() 的结构化结果。
    """

    items: list[
        DetectedItem
    ]

    needs_clarification: bool

    questions: list[
        ClarificationQuestion
    ]


# ============================================================
# 2. Market Comparable
# ============================================================

class ComparablePrice(BaseModel):
    """
    单个真实市场 comparable。
    """

    source_name: str

    source_url: str

    item_description: str

    original_price: float = Field(
        ge=0
    )

    original_currency: str

    price_cny: float = Field(
        ge=0
    )

    # comparable 与当前资产的相似程度
    # 0 ~ 1
    relevance: float = Field(
        ge=0,
        le=1
    )

    notes: str


class MarketSearchResult(BaseModel):
    """
    AI 搜索市场后返回的原始市场证据。

    最终价格仍然由 Python 计算。
    """

    enough_evidence: bool

    search_summary: str

    comparables: list[
        ComparablePrice
    ]


# ============================================================
# 3. Experience Overlay
# ============================================================

class ExperienceFactor(BaseModel):
    """
    真实物品上的体验 / 情境价值因素。

    注意：

    这里不直接输出人民币金额。

    AI 只负责描述：
    - 什么因素存在
    - 是增加还是降低体验价值
    - 影响有多强
    - 依据是什么

    最终人民币溢价由 Python 计算。
    """

    name: str

    direction: Literal[
        "raise",
        "lower",
        "neutral"
    ]

    strength: int = Field(
        ge=1,
        le=10
    )

    evidence: str


class ExperienceOverlayResult(BaseModel):
    """
    market / model 类型真实资产上的
    Experience Overlay。

    例子：

    冰可乐的第一口：
        市场基础价值
        +
        第一口体验溢价

    最后一张厕纸：
        物质基础价值
        +
        最后防线 / 即时需求溢价


    ----------------------------------------------------------
    核心原则
    ----------------------------------------------------------

    AI 不直接输出：

        experience_premium_cny
        final_value_cny

    AI 只输出无单位参数。

    Python 根据真实市场 anchor 计算金额。
    """

    # --------------------------------------------------------
    # 是否真的应该叠加体验价值
    # --------------------------------------------------------

    applicable: bool

    # --------------------------------------------------------
    # 市场锚点是什么
    #
    # 示例：
    #
    # "一整瓶冰镇可乐"
    # "一整卷同款厕纸"
    # "完整的一顿火锅"
    # --------------------------------------------------------

    anchor_description: str

    # --------------------------------------------------------
    # 当前对象占完整市场锚点的物质量比例
    #
    # 0 ~ 1
    #
    # 例如：
    #
    # 第一口可乐可能约占整瓶 0.08
    #
    # 一张厕纸可能约占整卷 0.005
    #
    # 如果估值对象本身就是完整商品：
    # 可以为 1
    # --------------------------------------------------------

    material_fraction: float = Field(
        ge=0,
        le=1
    )

    # --------------------------------------------------------
    # 该对象占完整体验价值的大致比例
    #
    # 0 ~ 1
    #
    # 例如：
    #
    # 冰可乐第一口：
    # material_fraction = 0.08
    #
    # 但：
    # experience_share = 0.45
    #
    # 表示：
    # 喝掉的量很少，
    # 却贡献了很大一部分体验。
    # --------------------------------------------------------

    experience_share: float = Field(
        ge=0,
        le=1
    )

    # --------------------------------------------------------
    # 当前特殊场景的强化程度
    #
    # 0 ~ 2
    #
    # 1.0：
    # 正常体验强度
    #
    # > 1：
    # 特殊环境进一步强化体验
    #
    # 例如：
    # 极渴时的冰可乐第一口
    # 最后一张厕纸的即时需求
    #
    # < 1：
    # 体验存在但较弱
    # --------------------------------------------------------

    context_intensity: float = Field(
        ge=0,
        le=2
    )

    # --------------------------------------------------------
    # UI 用的体验溢价名称
    #
    # AI 根据具体故事动态生成。
    #
    # 例如：
    #
    # "第一口爽感溢价"
    # "最后防线溢价"
    # "深夜救命溢价"
    # "仪式感溢价"
    # --------------------------------------------------------

    premium_label: str

    # --------------------------------------------------------
    # 最能解释为什么这个对象
    # 不应该只按照物质成本计算的具体细节
    # --------------------------------------------------------

    signature_detail: str

    # --------------------------------------------------------
    # 2~4 个动态体验因素
    # --------------------------------------------------------

    factors: list[
        ExperienceFactor
    ]

    # --------------------------------------------------------
    # 为什么形成这些参数
    # --------------------------------------------------------

    rationale: str

    # --------------------------------------------------------
    # A-Rank 风格评论
    # --------------------------------------------------------

    commentary: str


# ============================================================
# 4. Entertainment Valuation
# ============================================================

class PersonalizationFactor(BaseModel):
    """
    纯娱乐估值中的个性化因素。
    """

    name: str

    direction: Literal[
        "raise",
        "lower",
        "neutral"
    ]

    strength: int = Field(
        ge=1,
        le=10
    )

    evidence: str


class EntertainmentValuationResult(BaseModel):
    """
    完全不存在可靠真实市场价格的对象使用。

    例如：

    - 爱情
    - 青春
    - 友情
    - 回忆
    - 人生阶段
    """

    estimated_value_cny: float

    signature_detail: str

    personalization_factors: list[
        PersonalizationFactor
    ]

    rationale: str

    commentary: str

    disclaimer: str


# ============================================================
# 5. Commentary
# ============================================================

class CommentaryResult(BaseModel):
    """
    给真实资产生成最终 A-Rank 风格评价。
    """

    commentary: str

    footnote: str


# ============================================================
# JSON SCHEMAS
#
# 以下是真正发送给 OpenAI Structured Outputs 的格式。
#
# Pydantic Model 与这里必须保持同步。
# ============================================================


# ============================================================
# 1. Analysis JSON Schema
# ============================================================

ANALYSIS_JSON_FORMAT = {
    "type": "json_schema",

    "name": "analysis_result",

    "strict": True,

    "schema": {
        "type": "object",

        "properties": {

            "items": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "id": {
                            "type": "string"
                        },

                        "name": {
                            "type": "string"
                        },

                        "valuation_mode": {
                            "type": "string",

                            "enum": [
                                "market",
                                "model",
                                "entertainment"
                            ]
                        },

                        "category": {
                            "type": "string"
                        },

                        "known_information": {
                            "type": "array",

                            "items": {
                                "type": "string"
                            }
                        },

                        "experience_overlay": {
                            "type": "boolean"
                        }
                    },

                    "required": [
                        "id",
                        "name",
                        "valuation_mode",
                        "category",
                        "known_information",
                        "experience_overlay"
                    ],

                    "additionalProperties": False
                }
            },

            "needs_clarification": {
                "type": "boolean"
            },

            "questions": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "id": {
                            "type": "string"
                        },

                        "item_id": {
                            "type": "string"
                        },

                        "question": {
                            "type": "string"
                        },

                        "placeholder": {
                            "type": "string"
                        },

                        "reason": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "id",
                        "item_id",
                        "question",
                        "placeholder",
                        "reason"
                    ],

                    "additionalProperties": False
                }
            }
        },

        "required": [
            "items",
            "needs_clarification",
            "questions"
        ],

        "additionalProperties": False
    }
}


# ============================================================
# 2. Market Search JSON Schema
# ============================================================

MARKET_SEARCH_JSON_FORMAT = {
    "type": "json_schema",

    "name": "market_search_result",

    "strict": True,

    "schema": {
        "type": "object",

        "properties": {

            "enough_evidence": {
                "type": "boolean"
            },

            "search_summary": {
                "type": "string"
            },

            "comparables": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "source_name": {
                            "type": "string"
                        },

                        "source_url": {
                            "type": "string"
                        },

                        "item_description": {
                            "type": "string"
                        },

                        "original_price": {
                            "type": "number",
                            "minimum": 0
                        },

                        "original_currency": {
                            "type": "string"
                        },

                        "price_cny": {
                            "type": "number",
                            "minimum": 0
                        },

                        "relevance": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1
                        },

                        "notes": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "source_name",
                        "source_url",
                        "item_description",
                        "original_price",
                        "original_currency",
                        "price_cny",
                        "relevance",
                        "notes"
                    ],

                    "additionalProperties": False
                }
            }
        },

        "required": [
            "enough_evidence",
            "search_summary",
            "comparables"
        ],

        "additionalProperties": False
    }
}


# ============================================================
# 3. Experience Overlay JSON Schema
# ============================================================

EXPERIENCE_OVERLAY_JSON_FORMAT = {
    "type": "json_schema",

    "name": "experience_overlay_result",

    "strict": True,

    "schema": {
        "type": "object",

        "properties": {

            "applicable": {
                "type": "boolean"
            },

            "anchor_description": {
                "type": "string"
            },

            "material_fraction": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },

            "experience_share": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },

            "context_intensity": {
                "type": "number",
                "minimum": 0,
                "maximum": 2
            },

            "premium_label": {
                "type": "string"
            },

            "signature_detail": {
                "type": "string"
            },

            "factors": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "name": {
                            "type": "string"
                        },

                        "direction": {
                            "type": "string",

                            "enum": [
                                "raise",
                                "lower",
                                "neutral"
                            ]
                        },

                        "strength": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10
                        },

                        "evidence": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "name",
                        "direction",
                        "strength",
                        "evidence"
                    ],

                    "additionalProperties": False
                }
            },

            "rationale": {
                "type": "string"
            },

            "commentary": {
                "type": "string"
            }
        },

        "required": [
            "applicable",
            "anchor_description",
            "material_fraction",
            "experience_share",
            "context_intensity",
            "premium_label",
            "signature_detail",
            "factors",
            "rationale",
            "commentary"
        ],

        "additionalProperties": False
    }
}


# ============================================================
# 4. Entertainment JSON Schema
# ============================================================

ENTERTAINMENT_JSON_FORMAT = {
    "type": "json_schema",

    "name": "entertainment_valuation",

    "strict": True,

    "schema": {
        "type": "object",

        "properties": {

            "estimated_value_cny": {
                "type": "number"
            },

            "signature_detail": {
                "type": "string"
            },

            "personalization_factors": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "name": {
                            "type": "string"
                        },

                        "direction": {
                            "type": "string",

                            "enum": [
                                "raise",
                                "lower",
                                "neutral"
                            ]
                        },

                        "strength": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10
                        },

                        "evidence": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "name",
                        "direction",
                        "strength",
                        "evidence"
                    ],

                    "additionalProperties": False
                }
            },

            "rationale": {
                "type": "string"
            },

            "commentary": {
                "type": "string"
            },

            "disclaimer": {
                "type": "string"
            }
        },

        "required": [
            "estimated_value_cny",
            "signature_detail",
            "personalization_factors",
            "rationale",
            "commentary",
            "disclaimer"
        ],

        "additionalProperties": False
    }
}


# ============================================================
# 5. Commentary JSON Schema
# ============================================================

COMMENTARY_JSON_FORMAT = {
    "type": "json_schema",

    "name": "commentary_result",

    "strict": True,

    "schema": {
        "type": "object",

        "properties": {

            "commentary": {
                "type": "string"
            },

            "footnote": {
                "type": "string"
            }
        },

        "required": [
            "commentary",
            "footnote"
        ],

        "additionalProperties": False
    }
}