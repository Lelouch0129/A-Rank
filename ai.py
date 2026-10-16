# 所有 OpenAI API 调用

# ============================================================
# ai.py
# 所有 OpenAI API 调用
# ============================================================

import os
import json
import base64
from typing import Type, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from schemas import (
    AnalysisResult,
    MarketSearchResult,
    EntertainmentValuationResult,
    CommentaryResult,

    ANALYSIS_JSON_FORMAT,
    MARKET_SEARCH_JSON_FORMAT,
    ENTERTAINMENT_JSON_FORMAT,
    COMMENTARY_JSON_FORMAT
)

from prompts import (
    ANALYSIS_PROMPT,
    MARKET_SEARCH_PROMPT,
    ENTERTAINMENT_PROMPT,
    COMMENTARY_PROMPT
)


# ============================================================
# 环境变量 / OpenAI Client
# ============================================================

# ============================================================
# ai.py
# A-Rank 所有 OpenAI API 调用
# ============================================================

import os
import json
import base64

from typing import Type, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from schemas import (
    AnalysisResult,
    MarketSearchResult,
    ExperienceOverlayResult,
    EntertainmentValuationResult,
    CommentaryResult,

    ANALYSIS_JSON_FORMAT,
    MARKET_SEARCH_JSON_FORMAT,
    EXPERIENCE_OVERLAY_JSON_FORMAT,
    ENTERTAINMENT_JSON_FORMAT,
    COMMENTARY_JSON_FORMAT,
)

from prompts import (
    ANALYSIS_PROMPT,
    MARKET_SEARCH_PROMPT,
    EXPERIENCE_OVERLAY_PROMPT,
    ENTERTAINMENT_PROMPT,
    COMMENTARY_PROMPT,
)


# ============================================================
# Environment / Client
# ============================================================

load_dotenv()

client = OpenAI()


# ============================================================
# Models
# ============================================================

MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna",
)


ENTERTAINMENT_MODEL = os.getenv(
    "OPENAI_ENTERTAINMENT_MODEL",
    "gpt-5.6-terra",
)


# Experience Overlay 默认使用娱乐模型。
#
# 如果未来想单独换模型，
# 可以在 .env 中添加：
#
# OPENAI_EXPERIENCE_MODEL=xxx
#
EXPERIENCE_MODEL = os.getenv(
    "OPENAI_EXPERIENCE_MODEL",
    ENTERTAINMENT_MODEL,
)


# ============================================================
# Generic Type
# ============================================================

T = TypeVar(
    "T",
    bound=BaseModel,
)


# ============================================================
# Helper 1
# 图片 -> Data URL
# ============================================================

def image_to_data_url(
    image_bytes: bytes,
    mime_type: str,
) -> str:
    """
    将图片 bytes 转成 Responses API
    可以直接读取的 Data URL。
    """

    base64_image = base64.b64encode(
        image_bytes
    ).decode(
        "utf-8"
    )

    return (
        f"data:{mime_type};base64,"
        f"{base64_image}"
    )


# ============================================================
# Helper 2
# Structured Output Parser
# ============================================================

def parse_structured_response(
    response,
    schema_class: Type[T],
) -> T:
    """
    统一解析 OpenAI Structured Output。

    流程：

    response.output_text
        ↓
    JSON
        ↓
    Pydantic Validation
    """

    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if not output_text:

        raise ValueError(
            "OpenAI 没有返回可解析的 output_text。"
        )

    # ========================================================
    # JSON Parse
    # ========================================================

    try:

        data = json.loads(
            output_text
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "OpenAI 返回的内容不是有效 JSON。"
        ) from exc

    # ========================================================
    # Pydantic Validation
    # ========================================================

    try:

        return schema_class.model_validate(
            data
        )

    except Exception as exc:

        raise ValueError(
            f"OpenAI 返回的数据不符合 "
            f"{schema_class.__name__} 结构。"
        ) from exc


# ============================================================
# Helper 3
# Analysis Result Cleanup
# ============================================================

def clean_analysis_result(
    result: AnalysisResult,
) -> AnalysisResult:
    """
    对 Router 返回的结果做最后一道 Python 层保险。

    规则：

    1. question.item_id 必须真实存在
    2. question.id 不能重复
    3. 全局最多 3 个问题
    4. 没有问题时 needs_clarification=False
    5. entertainment 不允许 Experience Overlay
    """

    # ========================================================
    # Item IDs
    # ========================================================

    valid_item_ids = {
        item.id
        for item
        in result.items
    }

    # ========================================================
    # 强制保证：
    #
    # Pure Entertainment
    # 不能再叠 Experience Overlay
    # ========================================================

    for item in result.items:

        if (
            item.valuation_mode
            == "entertainment"
        ):

            item.experience_overlay = False

    # ========================================================
    # Questions
    # ========================================================

    cleaned_questions = []

    seen_question_ids = set()

    for question in result.questions:

        # ----------------------------------------------------
        # 无效 item_id
        # ----------------------------------------------------

        if (
            question.item_id
            not in valid_item_ids
        ):

            continue

        # ----------------------------------------------------
        # 重复问题 ID
        # ----------------------------------------------------

        if (
            question.id
            in seen_question_ids
        ):

            continue

        seen_question_ids.add(
            question.id
        )

        cleaned_questions.append(
            question
        )

        # ----------------------------------------------------
        # 整个输入全局最多 3 个问题
        # ----------------------------------------------------

        if (
            len(cleaned_questions)
            >= 3
        ):

            break

    result.questions = (
        cleaned_questions
    )

    result.needs_clarification = (
        len(
            result.questions
        )
        > 0
    )

    return result


# ============================================================
# 1. Analyze Input
# ============================================================

def analyze_input(
    user_text: str,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> AnalysisResult:
    """
    A-Rank Router。

    支持：

    - 纯文字
    - 纯图片
    - 文字 + 图片
    - 多物品
    - market / model / entertainment
    - Experience Overlay 判断


    AI 负责：

    1. 识别一个或多个 item
    2. 为每个 item 生成 ID
    3. 提取 known_information
    4. 判断 valuation_mode
    5. 判断 experience_overlay
    6. 最多生成 3 个 clarification questions


    AI 不负责：

    - 最终价格
    - A-Rank
    - 市场搜索
    """

    content = []

    # ========================================================
    # Text
    # ========================================================

    if user_text.strip():

        content.append({
            "type": "input_text",
            "text": user_text.strip(),
        })

    else:

        content.append({
            "type": "input_text",

            "text": (
                "用户没有提供文字描述。"
                "请根据上传图片识别需要估值的对象。"
            ),
        })

    # ========================================================
    # Image
    # ========================================================

    if (
        image_bytes
        is not None
    ):

        image_url = (
            image_to_data_url(
                image_bytes,
                mime_type
                or "image/jpeg",
            )
        )

        content.append({
            "type": "input_image",
            "image_url": image_url,
            "detail": "auto",
        })

    # ========================================================
    # Request
    # ========================================================

    response = (
        client.responses.create(

            model=MODEL,

            input=[
                {
                    "role":
                        "developer",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                ANALYSIS_PROMPT,
                        }
                    ],
                },

                {
                    "role":
                        "user",

                    "content":
                        content,
                },
            ],

            text={
                "format":
                    ANALYSIS_JSON_FORMAT
            },
        )
    )

    # ========================================================
    # Parse
    # ========================================================

    result = (
        parse_structured_response(
            response,
            AnalysisResult,
        )
    )

    # ========================================================
    # Python Cleanup
    # ========================================================

    result = (
        clean_analysis_result(
            result
        )
    )

    return result


# ============================================================
# 2. Search Market Comparables
# ============================================================

def search_market_comparables(
    valuation_context: str,
) -> MarketSearchResult:
    """
    为单个 market / model item
    搜索真实市场 comparable。

    对 Experience Overlay 对象：

    这里搜索的是完整市场 anchor。

    例如：

    冰可乐第一口
        ↓
    搜整瓶可乐价格

    最后一张厕纸
        ↓
    搜整卷 / 整包厕纸价格


    AI：

    - 搜索价格
    - 整理 comparable
    - relevance
    - CNY 换算

    Python：

    - 异常值过滤
    - 最终价格计算
    """

    if not (
        valuation_context.strip()
    ):

        raise ValueError(
            "valuation_context 不能为空。"
        )

    response = (
        client.responses.create(

            model=MODEL,

            tools=[
                {
                    "type":
                        "web_search"
                }
            ],

            input=[
                {
                    "role":
                        "developer",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                MARKET_SEARCH_PROMPT,
                        }
                    ],
                },

                {
                    "role":
                        "user",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                valuation_context.strip(),
                        }
                    ],
                },
            ],

            text={
                "format":
                    MARKET_SEARCH_JSON_FORMAT
            },
        )
    )

    return (
        parse_structured_response(
            response,
            MarketSearchResult,
        )
    )


# ============================================================
# 3. Experience Overlay
# ============================================================

def estimate_experience_overlay(
    valuation_context: str,
) -> ExperienceOverlayResult:
    """
    为一个真实资产分析 Experience Overlay。

    只在：

        item.experience_overlay == True

    时调用。


    ----------------------------------------------------------
    AI 输出
    ----------------------------------------------------------

    applicable

    anchor_description

    material_fraction

    experience_share

    context_intensity

    premium_label

    signature_detail

    factors

    rationale

    commentary


    ----------------------------------------------------------
    AI 不输出
    ----------------------------------------------------------

    人民币溢价金额

    最终人民币价值

    A-Rank


    最终金额完全由 valuation.py 计算。
    """

    if not (
        valuation_context.strip()
    ):

        raise ValueError(
            "valuation_context 不能为空。"
        )

    response = (
        client.responses.create(

            model=EXPERIENCE_MODEL,

            input=[
                {
                    "role":
                        "developer",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                EXPERIENCE_OVERLAY_PROMPT,
                        }
                    ],
                },

                {
                    "role":
                        "user",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                valuation_context.strip(),
                        }
                    ],
                },
            ],

            text={
                "format":
                    EXPERIENCE_OVERLAY_JSON_FORMAT
            },
        )
    )

    result = (
        parse_structured_response(
            response,
            ExperienceOverlayResult,
        )
    )

    # ========================================================
    # Python Safety Clamp
    #
    # Pydantic / JSON Schema 本身已经限制范围，
    # 这里再做一道保险。
    # ========================================================

    result.material_fraction = max(
        0.0,
        min(
            float(
                result.material_fraction
            ),
            1.0,
        ),
    )

    result.experience_share = max(
        0.0,
        min(
            float(
                result.experience_share
            ),
            1.0,
        ),
    )

    result.context_intensity = max(
        0.0,
        min(
            float(
                result.context_intensity
            ),
            2.0,
        ),
    )

    # ========================================================
    # 如果 Overlay 最终被判定为不适用，
    # 强制所有价值参数归零。
    #
    # 避免出现：
    #
    # applicable=False
    # 但 experience_share=0.8
    # ========================================================

    if not result.applicable:

        result.experience_share = 0.0

        result.context_intensity = 0.0

    return result


# ============================================================
# 4. Pure Entertainment Valuation
# ============================================================

def estimate_entertainment_value(
    valuation_context: str,
) -> EntertainmentValuationResult:
    """
    给 Pure Entertainment 对象估值。

    例如：

    - 青春
    - 爱情
    - 友情
    - 回忆
    - 人生阶段


    与 Experience Overlay 不同：

    Pure Entertainment 没有真实市场 anchor。
    """

    if not (
        valuation_context.strip()
    ):

        raise ValueError(
            "valuation_context 不能为空。"
        )

    response = (
        client.responses.create(

            model=ENTERTAINMENT_MODEL,

            input=[
                {
                    "role":
                        "developer",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                ENTERTAINMENT_PROMPT,
                        }
                    ],
                },

                {
                    "role":
                        "user",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                valuation_context.strip(),
                        }
                    ],
                },
            ],

            text={
                "format":
                    ENTERTAINMENT_JSON_FORMAT
            },
        )
    )

    result = (
        parse_structured_response(
            response,
            EntertainmentValuationResult,
        )
    )

    # ========================================================
    # 娱乐估值必须 > 0
    # ========================================================

    if (
        result
        .estimated_value_cny
        <= 0
    ):

        result.estimated_value_cny = (
            1.0
        )

    return result


# ============================================================
# 5. Real Asset Commentary
# ============================================================

def generate_commentary(
    item_name: str,
    value_cny: float,
    a_rank: float,
    valuation_type: str,
    market_summary: str,
) -> CommentaryResult:
    """
    给普通 market / model 真实资产
    生成 A-Rank 风格评价。

    Experience Overlay 对象：

    后续 app.py 会优先使用
    Experience Overlay 自己生成的 commentary。

    因此这里主要服务于：

        experience_overlay == False

    的真实资产。


    AI 不重新决定价格。
    """

    user_input = f"""
对象：
{item_name}

最终估值：
¥{value_cny:.2f}

A-Rank：
A{a_rank:.2f}

估值方式：
{valuation_type}

市场信息：
{market_summary}
""".strip()

    response = (
        client.responses.create(

            model=MODEL,

            input=[
                {
                    "role":
                        "developer",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                COMMENTARY_PROMPT,
                        }
                    ],
                },

                {
                    "role":
                        "user",

                    "content": [
                        {
                            "type":
                                "input_text",

                            "text":
                                user_input,
                        }
                    ],
                },
            ],

            text={
                "format":
                    COMMENTARY_JSON_FORMAT
            },
        )
    )

    return (
        parse_structured_response(
            response,
            CommentaryResult,
        )
    )