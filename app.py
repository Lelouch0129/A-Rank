# ============================================================
# app.py
# A-Rank Streamlit UI
# ============================================================

import streamlit as st

from ai import (
    analyze_input,
    search_market_comparables,
    estimate_experience_overlay,
    estimate_entertainment_value,
    generate_commentary,
)

from valuation import (
    calculate_real_asset_valuation,
    calculate_experience_overlay_valuation,
    calculate_a_rank,
)


st.set_page_config(
    page_title="A-Rank",
    page_icon="A",
    layout="centered",
)


MODE_LABELS = {
    "market": "市场估值",
    "model": "模型估值",
    "entertainment": "娱乐估值",
}


# ============================================================
# Session State
# ============================================================

def initialize_state():
    defaults = {
        "stage": "INPUT",
        "original_text": "",
        "image_bytes": None,
        "image_mime": None,
        "analysis": None,
        "clarification_answers": {},
        "result": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_app():
    for key in [
        "stage",
        "original_text",
        "image_bytes",
        "image_mime",
        "analysis",
        "clarification_answers",
        "result",
    ]:
        st.session_state.pop(
            key,
            None,
        )

    st.rerun()


initialize_state()


# ============================================================
# Helpers
# ============================================================

def get_item_by_id(
    item_id: str
):
    analysis = (
        st.session_state.analysis
    )

    if analysis is None:
        return None

    for item in analysis.items:

        if item.id == item_id:
            return item

    return None


def build_item_context(
    item
) -> str:
    """
    为每个 item 建立独立估值上下文。

    只加入：

    - 用户原始描述
    - 当前 item 信息
    - 当前 item 对应的 clarification answers

    不把其他 item 的回答混进来。
    """

    original_text = (
        st.session_state
        .original_text
        .strip()
        or
        "用户未提供额外文字描述，"
        "主要信息来自上传图片。"
    )

    lines = [
        "用户原始描述：",
        original_text,
        "",
        "当前待估对象：",
        item.name,
        "",
        "对象 ID：",
        item.id,
        "",
        "类别：",
        item.category,
        "",
        "估值模式：",
        item.valuation_mode,
        "",
        "是否启用 Experience Overlay：",
        str(
            item.experience_overlay
        ),
        "",
        "已经确认的信息：",
    ]

    if item.known_information:

        lines.extend(
            f"- {info}"
            for info
            in item.known_information
        )

    else:

        lines.append(
            "- 暂无额外确认信息"
        )

    relevant_answers = [
        data
        for data
        in (
            st.session_state
            .clarification_answers
            .values()
        )
        if (
            data.get(
                "item_id"
            )
            == item.id

            and

            data.get(
                "answer",
                "",
            ).strip()
        )
    ]

    if relevant_answers:

        lines.extend([
            "",
            "用户补充的信息：",
        ])

        for data in relevant_answers:

            lines.append(
                f"- "
                f"{data['question']}: "
                f"{data['answer']}"
            )

    return "\n".join(
        lines
    )


def calculate_overall_confidence(
    item_results
):
    """
    总体 Confidence 只计算真实资产。

    Entertainment 不参与真实资产综合置信度。

    多个真实资产之间：

    按最终估值金额加权。
    """

    real_asset_items = [
        item
        for item
        in item_results
        if (
            item["type"]
            == "real_asset"

            and

            item.get(
                "confidence"
            )
            is not None

            and

            item.get(
                "best_estimate",
                0,
            )
            > 0
        )
    ]

    if not real_asset_items:
        return None

    total_value = sum(
        item[
            "best_estimate"
        ]
        for item
        in real_asset_items
    )

    if total_value <= 0:
        return None

    weighted_confidence = (
        sum(
            item[
                "confidence"
            ]
            *
            item[
                "best_estimate"
            ]

            for item
            in real_asset_items
        )
        /
        total_value
    )

    return round(
        weighted_confidence
    )


# ============================================================
# Multi-item Valuation
# ============================================================

def perform_valuation(
    status=None
):

    analysis = (
        st.session_state
        .analysis
    )

    if (
        analysis is None
        or not analysis.items
    ):

        raise ValueError(
            "没有可用于估值的分析结果。"
        )

    item_results = []

    # ========================================================
    # 每个 item 独立估值
    # ========================================================

    for index, item in enumerate(
        analysis.items,
        start=1,
    ):

        context = (
            build_item_context(
                item
            )
        )

        mode_label = (
            MODE_LABELS.get(
                item.valuation_mode,
                item.valuation_mode,
            )
        )

        if status:

            status.write(
                f"正在估值 "
                f"{index}/"
                f"{len(analysis.items)}："
                f"{item.name}"
            )

        try:

            # ====================================================
            # 1. Pure Entertainment
            # ====================================================

            if (
                item.valuation_mode
                == "entertainment"
            ):

                entertainment = (
                    estimate_entertainment_value(
                        context
                    )
                )

                value = max(
                    float(
                        entertainment
                        .estimated_value_cny
                    ),
                    1.0,
                )

                item_results.append({

                    "id":
                        item.id,

                    "name":
                        item.name,

                    "category":
                        item.category,

                    "valuation_mode":
                        item.valuation_mode,

                    "type":
                        "entertainment",

                    "best_estimate":
                        value,

                    "low_estimate":
                        value,

                    "high_estimate":
                        value,

                    "a_rank":
                        calculate_a_rank(
                            value
                        ),

                    "confidence":
                        None,

                    "signature_detail":
                        entertainment
                        .signature_detail,

                    "personalization_factors":
                        entertainment
                        .personalization_factors,

                    "rationale":
                        entertainment
                        .rationale,

                    "commentary":
                        entertainment
                        .commentary,

                    "footnote":
                        entertainment
                        .disclaimer,
                })

                if status:

                    status.write(
                        f"✓ "
                        f"{item.name}："
                        f"完成娱乐估值"
                    )

                continue


            # ====================================================
            # 2. Market / Model
            # ====================================================

            if (
                item.valuation_mode
                not in {
                    "market",
                    "model",
                }
            ):

                raise ValueError(
                    f"未知估值模式："
                    f"{item.valuation_mode}"
                )


            # ====================================================
            # 2A. Search Market Anchor / Comparables
            # ====================================================

            market_data = (
                search_market_comparables(
                    context
                )
            )

            if not (
                market_data
                .comparables
            ):

                raise ValueError(
                    "没有找到可用于计算的"
                    "市场参考。"
                )


            # ====================================================
            # 2B. Python Base Market Valuation
            #
            # 对普通商品：
            #
            # 就是最终基础市场价值。
            #
            # 对 Experience Overlay：
            #
            # 这里代表完整市场 Anchor。
            # ====================================================

            anchor_valuation = (
                calculate_real_asset_valuation(

                    comparables=(
                        market_data
                        .comparables
                    ),

                    valuation_mode=(
                        item
                        .valuation_mode
                    ),

                    enough_evidence=(
                        market_data
                        .enough_evidence
                    ),
                )
            )


            # ====================================================
            # 3. Experience Overlay
            # ====================================================

            if (
                item.experience_overlay
            ):

                if status:

                    status.write(
                        f"↳ "
                        f"{item.name}："
                        f"分析体验 / 情境溢价"
                    )

                # ------------------------------------------------
                # AI：
                #
                # 只给无单位 Experience 参数。
                #
                # 不给人民币金额。
                # ------------------------------------------------

                overlay = (
                    estimate_experience_overlay(
                        context
                    )
                )

                # ------------------------------------------------
                # Python：
                #
                # Market Anchor
                # +
                # Experience 参数
                #
                # → 最终人民币价值
                # ------------------------------------------------

                final_valuation = (
                    calculate_experience_overlay_valuation(

                        anchor_valuation=(
                            anchor_valuation
                        ),

                        overlay=(
                            overlay
                        ),
                    )
                )


                # =================================================
                # Experience 确认适用
                # =================================================

                if overlay.applicable:

                    commentary_text = (
                        overlay
                        .commentary
                    )

                    footnote_text = (
                        "市场基础价值来自当前公开市场参考；"
                        "体验溢价为 A-Rank 娱乐化情境模型，"
                        "不代表真实市场、公允、"
                        "会计或法律价值。"
                    )


                # =================================================
                # Router 初步判断可能适用
                #
                # 但 Overlay 模块复核认为不适用
                # =================================================

                else:

                    commentary = (
                        generate_commentary(

                            item_name=(
                                item.name
                            ),

                            value_cny=(
                                final_valuation[
                                    "best_estimate"
                                ]
                            ),

                            a_rank=(
                                final_valuation[
                                    "a_rank"
                                ]
                            ),

                            valuation_type=(
                                item
                                .valuation_mode
                            ),

                            market_summary=(
                                market_data
                                .search_summary
                            ),
                        )
                    )

                    commentary_text = (
                        commentary
                        .commentary
                    )

                    footnote_text = (
                        commentary
                        .footnote
                    )


                # =================================================
                # 保存 Experience Overlay Result
                # =================================================

                item_results.append({

                    "id":
                        item.id,

                    "name":
                        item.name,

                    "category":
                        item.category,

                    "valuation_mode":
                        item.valuation_mode,

                    "type":
                        "real_asset",


                    # =============================================
                    # Final A-Rank Value
                    # =============================================

                    "best_estimate":
                        final_valuation[
                            "best_estimate"
                        ],

                    "low_estimate":
                        final_valuation[
                            "low_estimate"
                        ],

                    "high_estimate":
                        final_valuation[
                            "high_estimate"
                        ],

                    "a_rank":
                        final_valuation[
                            "a_rank"
                        ],

                    "confidence":
                        final_valuation[
                            "confidence"
                        ],


                    # =============================================
                    # Market
                    # =============================================

                    "market_summary":
                        market_data
                        .search_summary,

                    "market_enough_evidence":
                        market_data
                        .enough_evidence,

                    "comparables":
                        final_valuation[
                            "comparables_used"
                        ],

                    "representative":
                        final_valuation.get(
                            "representative_comparable"
                        ),

                    "valuation_method":
                        final_valuation[
                            "valuation_method"
                        ],


                    # =============================================
                    # Experience Overlay
                    # =============================================

                    "experience_overlay_requested":
                        True,

                    "experience_overlay":
                        final_valuation[
                            "experience_overlay"
                        ],

                    "anchor_description":
                        final_valuation[
                            "anchor_description"
                        ],

                    "anchor_best_estimate":
                        final_valuation[
                            "anchor_best_estimate"
                        ],

                    "market_confidence":
                        final_valuation[
                            "market_confidence"
                        ],

                    "material_fraction":
                        final_valuation[
                            "material_fraction"
                        ],

                    "material_value":
                        final_valuation[
                            "material_value"
                        ],

                    "experience_share":
                        final_valuation[
                            "experience_share"
                        ],

                    "context_intensity":
                        final_valuation[
                            "context_intensity"
                        ],

                    "experience_premium":
                        final_valuation[
                            "experience_premium"
                        ],

                    "premium_label":
                        final_valuation[
                            "premium_label"
                        ],

                    "experience_multiplier":
                        final_valuation[
                            "experience_multiplier"
                        ],

                    "premium_vs_material":
                        final_valuation[
                            "premium_vs_material"
                        ],

                    "signature_detail":
                        final_valuation[
                            "signature_detail"
                        ],

                    "experience_factors":
                        final_valuation[
                            "experience_factors"
                        ],

                    "experience_rationale":
                        final_valuation[
                            "experience_rationale"
                        ],


                    # =============================================
                    # Commentary
                    # =============================================

                    "commentary":
                        commentary_text,

                    "footnote":
                        footnote_text,
                })


                if status:

                    if overlay.applicable:

                        status.write(
                            f"✓ "
                            f"{item.name}："
                            f"完成{mode_label}"
                            f" + Experience Overlay"
                        )

                    else:

                        status.write(
                            f"✓ "
                            f"{item.name}："
                            f"体验溢价复核后未启用"
                        )

                continue


            # ====================================================
            # 4. Normal Market / Model Asset
            # ====================================================

            commentary = (
                generate_commentary(

                    item_name=(
                        item.name
                    ),

                    value_cny=(
                        anchor_valuation[
                            "best_estimate"
                        ]
                    ),

                    a_rank=(
                        anchor_valuation[
                            "a_rank"
                        ]
                    ),

                    valuation_type=(
                        item
                        .valuation_mode
                    ),

                    market_summary=(
                        market_data
                        .search_summary
                    ),
                )
            )


            item_results.append({

                "id":
                    item.id,

                "name":
                    item.name,

                "category":
                    item.category,

                "valuation_mode":
                    item.valuation_mode,

                "type":
                    "real_asset",

                "best_estimate":
                    anchor_valuation[
                        "best_estimate"
                    ],

                "low_estimate":
                    anchor_valuation[
                        "low_estimate"
                    ],

                "high_estimate":
                    anchor_valuation[
                        "high_estimate"
                    ],

                "a_rank":
                    anchor_valuation[
                        "a_rank"
                    ],

                "confidence":
                    anchor_valuation[
                        "confidence"
                    ],

                "commentary":
                    commentary
                    .commentary,

                "footnote":
                    commentary
                    .footnote,

                "market_summary":
                    market_data
                    .search_summary,

                "market_enough_evidence":
                    market_data
                    .enough_evidence,

                "comparables":
                    anchor_valuation[
                        "comparables_used"
                    ],

                "representative":
                    anchor_valuation.get(
                        "representative_comparable"
                    ),

                "valuation_method":
                    anchor_valuation.get(
                        "valuation_method"
                    ),

                "experience_overlay_requested":
                    False,

                "experience_overlay":
                    False,
            })


            if status:

                status.write(
                    f"✓ "
                    f"{item.name}："
                    f"完成{mode_label}"
                )


        except Exception as exc:

            # ====================================================
            # 单个 Item 失败不影响其他 Item
            # ====================================================

            item_results.append({

                "id":
                    item.id,

                "name":
                    item.name,

                "category":
                    item.category,

                "valuation_mode":
                    item.valuation_mode,

                "type":
                    "error",

                "error":
                    str(exc),
            })


            if status:

                status.write(
                    f"⚠ "
                    f"{item.name}："
                    f"估值失败，已跳过"
                )


    # ========================================================
    # Total
    # ========================================================

    successful_items = [
        item
        for item
        in item_results
        if (
            item["type"]
            != "error"
        )
    ]

    if not successful_items:

        raise ValueError(
            "所有对象都估值失败，"
            "请补充更具体的信息后重试。"
        )


    # ========================================================
    # 总人民币价值
    # ========================================================

    total_best = sum(
        item[
            "best_estimate"
        ]
        for item
        in successful_items
    )

    total_low = sum(
        item[
            "low_estimate"
        ]
        for item
        in successful_items
    )

    total_high = sum(
        item[
            "high_estimate"
        ]
        for item
        in successful_items
    )


    # ========================================================
    # Result
    # ========================================================

    st.session_state.result = {

        "type":
            "multi_item",

        "item_count":
            len(
                item_results
            ),

        "successful_count":
            len(
                successful_items
            ),

        "failed_count":
            (
                len(
                    item_results
                )
                -
                len(
                    successful_items
                )
            ),

        "items":
            item_results,

        "best_estimate":
            round(
                total_best,
                2,
            ),

        "low_estimate":
            round(
                total_low,
                2,
            ),

        "high_estimate":
            round(
                total_high,
                2,
            ),

        # ====================================================
        # Multi-item:
        #
        # 先加总人民币价值
        #
        # 再计算 Total A-Rank
        # ====================================================

        "a_rank":
            calculate_a_rank(
                total_best
            ),

        "overall_confidence":
            calculate_overall_confidence(
                successful_items
            ),
    }


# ============================================================
# Result UI
# ============================================================

def render_entertainment_details(
    item
):

    st.caption(
        "Entertainment Estimate"
    )

    st.write(
        f"**¥"
        f"{item['best_estimate']:,.0f}"
        f" · "
        f"A{item['a_rank']:.2f}"
        f"**"
    )


    # ========================================================
    # Signature Detail
    # ========================================================

    if item.get(
        "signature_detail"
    ):

        st.info(
            item[
                "signature_detail"
            ]
        )


    st.write(
        item[
            "commentary"
        ]
    )

    st.caption(
        item[
            "footnote"
        ]
    )


    # ========================================================
    # Personalization Factors
    # ========================================================

    with st.expander(
        f"为什么这样估值："
        f"{item['name']}"
    ):

        if item.get(
            "rationale"
        ):

            st.write(
                item[
                    "rationale"
                ]
            )


        factors = item.get(
            "personalization_factors",
            [],
        )


        for factor in factors:

            if (
                factor.direction
                == "raise"
            ):

                symbol = "↑"

            elif (
                factor.direction
                == "lower"
            ):

                symbol = "↓"

            else:

                symbol = "→"


            st.markdown(
                f"**"
                f"{symbol} "
                f"{factor.name}"
                f"**"
            )


            st.write(
                f"影响强度："
                f"{factor.strength}/10"
            )


            st.caption(
                factor.evidence
            )

            st.divider()


def render_experience_overlay_details(
    item
):
    """
    展示：

        Market Anchor
            ↓
        Material Value
            +
        Experience Premium
            ↓
        A-Rank Value
    """

    st.caption(
        "Market + Experience Overlay"
    )


    # ========================================================
    # Final Value
    # ========================================================

    st.write(
        f"**¥"
        f"{item['best_estimate']:,.2f}"
        f" · "
        f"A{item['a_rank']:.2f}"
        f"**"
    )


    # ========================================================
    # Value Breakdown
    # ========================================================

    st.markdown(
        "#### 价值拆解"
    )


    col1, col2 = (
        st.columns(
            2
        )
    )


    with col1:

        st.metric(
            "物质价值",
            f"¥"
            f"{item['material_value']:,.2f}",
        )


    with col2:

        st.metric(
            item.get(
                "premium_label",
                "体验溢价",
            ),

            f"¥"
            f"{item['experience_premium']:,.2f}",
        )


    # ========================================================
    # Market Anchor
    # ========================================================

    st.caption(
        f"市场 Anchor："
        f"{item.get(
            'anchor_description',
            '完整市场商品',
        )}"
        f" · "
        f"约 ¥"
        f"{item.get(
            'anchor_best_estimate',
            0,
        ):,.2f}"
    )


    # ========================================================
    # Signature Detail
    # ========================================================

    if item.get(
        "signature_detail"
    ):

        st.info(
            item[
                "signature_detail"
            ]
        )


    # ========================================================
    # Experience Parameters
    # ========================================================

    material_fraction = (
        item.get(
            "material_fraction",
            0,
        )
    )

    experience_share = (
        item.get(
            "experience_share",
            0,
        )
    )


    st.caption(
        f"物质量占比："
        f"{material_fraction * 100:.1f}%"
        f" · "
        f"体验价值占比："
        f"{experience_share * 100:.1f}%"
        f" · "
        f"场景强度："
        f"{item.get(
            'context_intensity',
            0,
        ):.2f}×"
    )


    # ========================================================
    # Premium vs Material
    # ========================================================

    premium_vs_material = (
        item.get(
            "premium_vs_material"
        )
    )


    if (
        premium_vs_material
        is not None
        and
        premium_vs_material
        >= 1
    ):

        st.success(
            f"这次体验溢价约为"
            f"纯物质价值的 "
            f"{premium_vs_material:,.1f} 倍。"
        )


    # ========================================================
    # Commentary
    # ========================================================

    st.write(
        item[
            "commentary"
        ]
    )

    st.caption(
        item[
            "footnote"
        ]
    )


    # ========================================================
    # Experience Factors
    # ========================================================

    with st.expander(
        f"为什么有这笔溢价："
        f"{item['name']}"
    ):

        if item.get(
            "experience_rationale"
        ):

            st.write(
                item[
                    "experience_rationale"
                ]
            )


        factors = item.get(
            "experience_factors",
            [],
        )


        for factor in factors:

            if (
                factor.direction
                == "raise"
            ):

                symbol = "↑"

            elif (
                factor.direction
                == "lower"
            ):

                symbol = "↓"

            else:

                symbol = "→"


            st.markdown(
                f"**"
                f"{symbol} "
                f"{factor.name}"
                f"**"
            )


            st.write(
                f"影响强度："
                f"{factor.strength}/10"
            )


            st.caption(
                factor.evidence
            )

            st.divider()


def render_market_details(
    item
):

    # ========================================================
    # Experience Overlay 真正启用
    # ========================================================

    if item.get(
        "experience_overlay",
        False,
    ):

        render_experience_overlay_details(
            item
        )

        return


    # ========================================================
    # Normal Market / Model
    # ========================================================

    if (
        item[
            "valuation_mode"
        ]
        == "market"
    ):

        mode_text = (
            "Market Valuation"
        )

    else:

        mode_text = (
            "Model Valuation"
            " · "
            "V1 Comparable Proxy"
        )


    st.caption(
        mode_text
    )


    st.write(
        f"**¥"
        f"{item['best_estimate']:,.0f}"
        f" · "
        f"A{item['a_rank']:.2f}"
        f"**"
    )


    # ========================================================
    # Range
    # ========================================================

    if (
        item[
            "low_estimate"
        ]
        !=
        item[
            "high_estimate"
        ]
    ):

        st.caption(
            f"估值区间："
            f"¥"
            f"{item['low_estimate']:,.0f}"
            f" — "
            f"¥"
            f"{item['high_estimate']:,.0f}"
        )


    # ========================================================
    # Confidence
    # ========================================================

    confidence = (
        item.get(
            "confidence"
        )
    )


    if confidence is not None:

        st.caption(
            f"置信度："
            f"{confidence}%"
        )


    # ========================================================
    # Market Evidence Warning
    # ========================================================

    if not item.get(
        "market_enough_evidence",
        True,
    ):

        st.warning(
            "当前市场证据有限，"
            "因此该项估值的置信度"
            "已被自动限制。"
        )


    # ========================================================
    # Overlay 被检查但最终未启用
    # ========================================================

    if (
        item.get(
            "experience_overlay_requested",
            False,
        )

        and

        not item.get(
            "experience_overlay",
            False,
        )
    ):

        st.caption(
            "系统检查过体验 / 情境溢价，"
            "但当前信息不足以支持额外加成。"
        )


    st.write(
        item[
            "commentary"
        ]
    )

    st.caption(
        item[
            "footnote"
        ]
    )


# ============================================================
# Header
# ============================================================

st.title(
    "A-Rank"
)

st.caption(
    "万物皆可估值"
)


# ============================================================
# STAGE 1：INPUT
# ============================================================

if (
    st.session_state.stage
    == "INPUT"
):

    description = (
        st.text_area(

            "描述你想估值的东西",

            placeholder=(
                "例如："
                "我有一台用了两年的 MacBook、"
                "一瓶冰可乐的第一口、"
                "还有一段高中时期的爱情"
            ),

            height=120,
        )
    )


    st.write(
        "或者"
    )


    uploaded_file = (
        st.file_uploader(

            "上传一张图片",

            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
        )
    )


    if (
        uploaded_file
        is not None
    ):

        st.image(
            uploaded_file,

            caption=(
                "你上传的图片"
            ),

            width=300,
        )


    start_button = (
        st.button(

            "开始估值",

            type="primary",

            use_container_width=True,
        )
    )


    if start_button:

        if (
            not description.strip()
            and
            uploaded_file is None
        ):

            st.warning(
                "请输入文字或上传一张图片。"
            )


        else:

            # ====================================================
            # Save Input
            # ====================================================

            st.session_state[
                "original_text"
            ] = description


            # ====================================================
            # 清除上一轮状态
            # ====================================================

            st.session_state[
                "image_bytes"
            ] = None

            st.session_state[
                "image_mime"
            ] = None

            st.session_state[
                "clarification_answers"
            ] = {}

            st.session_state[
                "result"
            ] = None


            # ====================================================
            # Save Image
            # ====================================================

            if (
                uploaded_file
                is not None
            ):

                st.session_state[
                    "image_bytes"
                ] = (
                    uploaded_file
                    .getvalue()
                )

                st.session_state[
                    "image_mime"
                ] = (
                    uploaded_file
                    .type
                )


            # ====================================================
            # Analyze
            # ====================================================

            with st.status(

                "正在尝试估值...",

                expanded=True,

            ) as status:

                try:

                    analysis = (
                        analyze_input(

                            user_text=(
                                description
                            ),

                            image_bytes=(
                                st.session_state
                                .image_bytes
                            ),

                            mime_type=(
                                st.session_state
                                .image_mime
                            ),
                        )
                    )


                    if not (
                        analysis.items
                    ):

                        raise ValueError(
                            "没有识别到"
                            "可以估值的对象。"
                        )


                    st.session_state[
                        "analysis"
                    ] = analysis


                    status.write(
                        f"✓ 识别到 "
                        f"{len(analysis.items)} "
                        f"个待估对象"
                    )


                    # =================================================
                    # Display Detected Items
                    # =================================================

                    for item in (
                        analysis.items
                    ):

                        mode_label = (
                            MODE_LABELS.get(

                                item
                                .valuation_mode,

                                item
                                .valuation_mode,
                            )
                        )


                        overlay_label = (

                            " · 体验价值"

                            if (
                                item
                                .experience_overlay
                            )

                            else ""
                        )


                        status.write(
                            f"✓ "
                            f"{item.name}"
                            f" · "
                            f"{mode_label}"
                            f"{overlay_label}"
                        )


                        for info in (
                            item
                            .known_information[:2]
                        ):

                            status.write(
                                f"   · "
                                f"{info}"
                            )


                    # =================================================
                    # Clarification?
                    # =================================================

                    if (
                        analysis
                        .needs_clarification

                        and

                        analysis
                        .questions
                    ):

                        status.write(
                            "? 缺少影响估值的"
                            "关键信息"
                        )


                        st.session_state[
                            "stage"
                        ] = (
                            "CLARIFYING"
                        )


                    else:

                        status.write(
                            "✓ 当前信息足够"
                        )


                        st.session_state[
                            "stage"
                        ] = (
                            "VALUATING"
                        )


                    status.update(

                        label="分析完成",

                        state="complete",
                    )


                    st.rerun()


                except Exception as exc:

                    status.update(

                        label="分析失败",

                        state="error",
                    )


                    st.error(
                        f"错误："
                        f"{exc}"
                    )


# ============================================================
# STAGE 2：CLARIFYING
# ============================================================

elif (
    st.session_state.stage
    == "CLARIFYING"
):

    analysis = (
        st.session_state
        .analysis
    )


    st.write(
        "正在尝试估值..."
    )


    st.success(
        f"✓ 已识别 "
        f"{len(analysis.items)} "
        f"个待估对象"
    )


    # ========================================================
    # Display Items
    # ========================================================

    for item in (
        analysis.items
    ):

        mode_label = (
            MODE_LABELS.get(

                item
                .valuation_mode,

                item
                .valuation_mode,
            )
        )


        st.markdown(
            f"**"
            f"{item.name}"
            f"**"
        )


        caption = (
            f"{mode_label}"
            f" · "
            f"{item.category}"
        )


        if (
            item
            .experience_overlay
        ):

            caption += (
                " · "
                "Experience Overlay"
            )


        st.caption(
            caption
        )


        for info in (
            item
            .known_information
        ):

            st.write(
                f"✓ "
                f"{info}"
            )


    st.warning(
        "? 还缺少一些"
        "影响估值的关键信息"
    )


    st.subheader(
        "再告诉我一点，"
        "我能估得准很多"
    )


    # ========================================================
    # Global Maximum 3 Questions
    # ========================================================

    questions = (
        analysis
        .questions[:3]
    )


    with st.form(
        "clarification_form"
    ):

        form_values = []


        for index, q in enumerate(
            questions,
            start=1,
        ):

            related_item = (
                get_item_by_id(
                    q.item_id
                )
            )


            if (
                related_item
                is not None
            ):

                st.caption(
                    f"关于："
                    f"{related_item.name}"
                )


            st.markdown(
                f"### "
                f"{index}. "
                f"{q.question}"
            )


            if q.reason:

                st.caption(
                    q.reason
                )


            answer = (
                st.text_input(

                    q.question,

                    placeholder=(
                        q.placeholder
                    ),

                    key=(
                        f"answer_"
                        f"{q.id}"
                    ),

                    label_visibility=(
                        "collapsed"
                    ),
                )
            )


            skip = (
                st.checkbox(

                    "不知道 / 跳过",

                    key=(
                        f"skip_"
                        f"{q.id}"
                    ),
                )
            )


            form_values.append({

                "question_id":
                    q.id,

                "item_id":
                    q.item_id,

                "question":
                    q.question,

                "answer":
                    answer,

                "skip":
                    skip,
            })


            st.divider()


        submitted = (
            st.form_submit_button(

                "继续估值",

                type="primary",

                use_container_width=True,
            )
        )


        if submitted:

            answers = {}


            for data in (
                form_values
            ):

                final_answer = (

                    ""

                    if (
                        data[
                            "skip"
                        ]
                    )

                    else (
                        data[
                            "answer"
                        ].strip()
                    )
                )


                answers[
                    data[
                        "question_id"
                    ]
                ] = {

                    "item_id":
                        data[
                            "item_id"
                        ],

                    "question":
                        data[
                            "question"
                        ],

                    "answer":
                        final_answer,
                }


            st.session_state[
                "clarification_answers"
            ] = answers


            st.session_state[
                "stage"
            ] = (
                "VALUATING"
            )


            st.rerun()


# ============================================================
# STAGE 3：VALUATING
# ============================================================

elif (
    st.session_state.stage
    == "VALUATING"
):

    analysis = (
        st.session_state
        .analysis
    )


    with st.status(

        "正在估值...",

        expanded=True,

    ) as status:

        try:

            # =================================================
            # Count Modes
            # =================================================

            real_asset_count = (
                sum(
                    item.valuation_mode
                    in {
                        "market",
                        "model",
                    }

                    for item
                    in analysis.items
                )
            )


            overlay_count = (
                sum(
                    (
                        item.valuation_mode
                        in {
                            "market",
                            "model",
                        }
                    )

                    and

                    item.experience_overlay

                    for item
                    in analysis.items
                )
            )


            entertainment_count = (
                sum(
                    item.valuation_mode
                    == "entertainment"

                    for item
                    in analysis.items
                )
            )


            if real_asset_count:

                status.write(
                    f"准备处理 "
                    f"{real_asset_count} "
                    f"个真实资产对象"
                )


            if overlay_count:

                status.write(
                    f"其中 "
                    f"{overlay_count} "
                    f"个对象需要分析"
                    f"体验 / 情境价值"
                )


            if entertainment_count:

                status.write(
                    f"准备处理 "
                    f"{entertainment_count} "
                    f"个娱乐估值对象"
                )


            # =================================================
            # Perform Valuation
            # =================================================

            perform_valuation(
                status=status
            )


            result = (
                st.session_state
                .result
            )


            status.write(
                f"✓ 成功完成 "
                f"{result['successful_count']} "
                f"个对象的估值"
            )


            if (
                result[
                    "failed_count"
                ]
            ):

                status.write(
                    f"⚠ 有 "
                    f"{result['failed_count']} "
                    f"个对象暂时无法可靠估值"
                )


            status.write(
                "✓ 完成总价值计算"
            )


            status.write(
                "✓ 完成总 A-Rank 计算"
            )


            status.update(

                label="估值完成",

                state="complete",
            )


            st.session_state[
                "stage"
            ] = (
                "RESULT"
            )


            st.rerun()


        except Exception as exc:

            status.update(

                label="估值失败",

                state="error",
            )


            st.error(
                f"错误："
                f"{exc}"
            )


            if st.button(
                "重新开始"
            ):

                reset_app()


# ============================================================
# STAGE 4：RESULT
# ============================================================

elif (
    st.session_state.stage
    == "RESULT"
):

    result = (
        st.session_state
        .result
    )


    # ========================================================
    # Split Results
    # ========================================================

    successful_items = [
        item
        for item
        in result[
            "items"
        ]
        if (
            item[
                "type"
            ]
            != "error"
        )
    ]


    real_asset_items = [
        item
        for item
        in successful_items
        if (
            item[
                "type"
            ]
            == "real_asset"
        )
    ]


    failed_items = [
        item
        for item
        in result[
            "items"
        ]
        if (
            item[
                "type"
            ]
            == "error"
        )
    ]


    # ========================================================
    # Title
    # ========================================================

    if (
        result[
            "item_count"
        ]
        == 1

        and

        successful_items
    ):

        st.subheader(
            successful_items[
                0
            ][
                "name"
            ]
        )


    else:

        st.subheader(
            f"{result['successful_count']} "
            f"件对象的综合估值"
        )


    st.divider()


    # ========================================================
    # Total Range
    # ========================================================

    if (
        result[
            "low_estimate"
        ]
        !=
        result[
            "high_estimate"
        ]
    ):

        st.caption(
            "ESTIMATED TOTAL RANGE"
        )


        st.write(
            f"### ¥"
            f"{result['low_estimate']:,.0f}"
            f" — "
            f"¥"
            f"{result['high_estimate']:,.0f}"
        )


    # ========================================================
    # Best Estimate
    # ========================================================

    st.caption(
        "BEST ESTIMATE"
    )


    st.write(
        f"# ¥"
        f"{result['best_estimate']:,.2f}"
    )


    st.divider()


    # ========================================================
    # Total A-Rank
    # ========================================================

    st.caption(
        "TOTAL A-RANK"
    )


    st.write(
        f"# A"
        f"{result['a_rank']:.2f}"
    )


    # ========================================================
    # Overall Real Asset Confidence
    # ========================================================

    if (
        result[
            "overall_confidence"
        ]
        is not None
    ):

        confidence = (
            result[
                "overall_confidence"
            ]
        )


        st.caption(
            "真实资产综合估值置信度"
        )


        st.progress(
            confidence / 100
        )


        st.write(
            f"{confidence}%"
        )


    st.divider()


    # ========================================================
    # Item Details
    # ========================================================

    st.subheader(
        "估值明细"
    )


    for index, item in enumerate(
        successful_items,
        start=1,
    ):

        st.markdown(
            f"### "
            f"{index}. "
            f"{item['name']}"
        )


        if (
            item[
                "type"
            ]
            == "real_asset"
        ):

            render_market_details(
                item
            )


        elif (
            item[
                "type"
            ]
            == "entertainment"
        ):

            render_entertainment_details(
                item
            )


        st.divider()


    # ========================================================
    # Market References
    # ========================================================

    if real_asset_items:

        with st.expander(
            "查看市场参考"
        ):

            for item in (
                real_asset_items
            ):

                st.markdown(
                    f"### "
                    f"{item['name']}"
                )


                representative = (
                    item.get(
                        "representative"
                    )
                )


                if (
                    representative
                    is None
                ):

                    st.caption(
                        "暂时没有找到"
                        "足够可靠的"
                        "代表性市场参考。"
                    )

                    st.divider()

                    continue


                # =================================================
                # Overlay Anchor Explanation
                # =================================================

                if item.get(
                    "experience_overlay_requested",
                    False,
                ):

                    st.caption(
                        "该参考用于确定完整市场 Anchor，"
                        "不是直接把该商品价格"
                        "当作最终体验价值。"
                    )


                # =================================================
                # Comparable
                # =================================================

                st.write(
                    f"**"
                    f"{representative.item_description}"
                    f"**"
                )


                st.write(
                    f"参考价格："
                    f"约 ¥"
                    f"{representative.price_cny:,.2f}"
                )


                st.caption(
                    f"来源："
                    f"{representative.source_name}"
                )


                # =================================================
                # Link
                # =================================================

                if (
                    representative
                    .source_url
                ):

                    st.markdown(
                        f"[查看参考商品]"
                        f"("
                        f"{representative.source_url}"
                        f")"
                    )


                # =================================================
                # Notes
                # =================================================

                if (
                    representative
                    .notes
                ):

                    st.caption(
                        representative
                        .notes
                    )


                st.divider()


    # ========================================================
    # Failed Items
    # ========================================================

    if failed_items:

        with st.expander(
            "查看未成功估值的对象"
        ):

            for item in (
                failed_items
            ):

                st.markdown(
                    f"**"
                    f"{item['name']}"
                    f"**"
                )


                st.caption(
                    item[
                        "error"
                    ]
                )


                st.divider()


    # ========================================================
    # Reset
    # ========================================================

    st.divider()


    if st.button(

        "再估一个",

        use_container_width=True,
    ):

        reset_app()