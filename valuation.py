# ============================================================
# valuation.py
# A-Rank 确定性估值算法
#
# 负责：
# 1. 市场 comparable 清洗
# 2. 真实资产市场估值
# 3. Experience Overlay 确定性计算
# 4. Confidence
# 5. A-Rank
# ============================================================

import math
import statistics

from schemas import (
    ComparablePrice,
    ExperienceOverlayResult,
)


# ============================================================
# Constants
# ============================================================

# Experience Premium 的安全上限。
#
# 即使未来 AI 参数范围变化，
# 体验溢价也最多是完整市场 Anchor 的 3 倍。
#
# 当前 schema 中：
#
# experience_share <= 1
# context_intensity <= 2
#
# 理论上最多就是 2 倍，
# 这里额外保留一个安全层。
MAX_EXPERIENCE_PREMIUM_MULTIPLIER = 3.0


# ============================================================
# 1. A-Rank
# ============================================================

def calculate_a_rank(
    value_cny: float
) -> float:
    """
    A-Rank 统一公式：

        A = 1 + log10(V)

    V 单位为人民币元。

    示例：

        ¥1        -> A1.00
        ¥10       -> A2.00
        ¥100      -> A3.00
        ¥1,000    -> A4.00
        ¥10,000   -> A5.00
        ¥100,000  -> A6.00
    """

    if value_cny <= 0:
        return 0.0

    return round(
        1 + math.log10(value_cny),
        2
    )


# ============================================================
# 2. Comparable 基础过滤
# ============================================================

def filter_valid_comparables(
    comparables: list[ComparablePrice],
    min_relevance: float = 0.5
) -> list[ComparablePrice]:
    """
    删除明显不适合进入最终估值的数据。

    条件：

    - price_cny > 0
    - relevance >= min_relevance
    """

    return [
        item
        for item in comparables
        if (
            item.price_cny > 0
            and
            item.relevance >= min_relevance
        )
    ]


# ============================================================
# 3. MAD 异常值过滤
# ============================================================

def remove_outliers(
    comparables: list[ComparablePrice],
    min_relevance: float = 0.5
) -> list[ComparablePrice]:
    """
    使用 MAD：

    Median Absolute Deviation

    删除价格中的明显异常值。

    AI 负责：

    - 搜索
    - relevance

    Python 负责：

    - 是否进入最终估值
    - 是否属于统计异常值
    """

    valid = filter_valid_comparables(
        comparables,
        min_relevance=min_relevance,
    )

    # 0~2 条数据无法可靠判断统计异常
    if len(valid) <= 2:
        return valid

    prices = [
        item.price_cny
        for item in valid
    ]

    median_price = statistics.median(
        prices
    )

    deviations = [
        abs(
            price - median_price
        )
        for price in prices
    ]

    mad = statistics.median(
        deviations
    )

    # ========================================================
    # MAD = 0 fallback
    # ========================================================

    if mad == 0:

        lower_bound = (
            median_price
            * 0.5
        )

        upper_bound = (
            median_price
            * 1.5
        )

        cleaned = [
            item
            for item in valid
            if (
                lower_bound
                <= item.price_cny
                <= upper_bound
            )
        ]

        return (
            cleaned
            if cleaned
            else valid
        )

    # ========================================================
    # Robust Z-Score
    # ========================================================

    cleaned = []

    for item in valid:

        robust_z = (
            0.6745
            * abs(
                item.price_cny
                - median_price
            )
            / mad
        )

        if robust_z <= 3.5:

            cleaned.append(
                item
            )

    return (
        cleaned
        if cleaned
        else valid
    )


# ============================================================
# 4. Market Confidence
# ============================================================

def calculate_confidence(
    comparables: list[ComparablePrice],
    valuation_mode: str = "market",
    enough_evidence: bool = True
) -> int:
    """
    A-Rank V1 真实市场估值 Confidence。

    组成：

    40 分
        comparable 数量

    35 分
        市场价格一致性

    25 分
        comparable relevance


    model：

        因为 V1 目前只是 Comparable Proxy，
        Confidence 最大 80。


    enough_evidence=False：

        Confidence 最大 55。
    """

    count = len(
        comparables
    )

    if count == 0:
        return 0

    # ========================================================
    # 1. Comparable 数量
    # ========================================================

    count_score = (
        min(
            count / 6,
            1
        )
        * 40
    )

    # ========================================================
    # 2. 价格一致性
    # ========================================================

    prices = [
        item.price_cny
        for item in comparables
    ]

    if count == 1:

        consistency_score = 8

    else:

        median_price = (
            statistics.median(
                prices
            )
        )

        if median_price <= 0:

            consistency_score = 0

        else:

            std = (
                statistics.pstdev(
                    prices
                )
            )

            coefficient_of_variation = (
                std
                / median_price
            )

            consistency_score = (
                max(
                    0,
                    1 - min(
                        coefficient_of_variation,
                        1
                    )
                )
                * 35
            )

    # ========================================================
    # 3. Relevance
    # ========================================================

    average_relevance = (
        statistics.mean(
            item.relevance
            for item in comparables
        )
    )

    relevance_score = (
        max(
            0,
            min(
                average_relevance,
                1
            )
        )
        * 25
    )

    confidence = round(
        count_score
        + consistency_score
        + relevance_score
    )

    # ========================================================
    # Evidence Cap
    # ========================================================

    if not enough_evidence:

        confidence = min(
            confidence,
            55
        )

    # ========================================================
    # Model Cap
    # ========================================================

    if valuation_mode == "model":

        confidence = min(
            confidence,
            80
        )

    return max(
        0,
        min(
            confidence,
            100
        )
    )


# ============================================================
# 5. Representative Comparable
# ============================================================

def select_representative_comparable(
    comparables: list[ComparablePrice],
    best_estimate: float
) -> ComparablePrice | None:
    """
    选择结果页展示的一个代表性市场参考。

    优先：

    1. 有真实 URL
    2. relevance 高
    3. 价格接近最终市场中位数
    """

    if not comparables:
        return None

    with_url = [
        item
        for item in comparables
        if item.source_url.strip()
    ]

    candidates = (
        with_url
        if with_url
        else comparables
    )

    return max(
        candidates,

        key=lambda item: (
            item.relevance,

            -abs(
                item.price_cny
                - best_estimate
            )
        )
    )


# ============================================================
# 6. Market / Model Base Valuation
# ============================================================

def calculate_market_valuation(
    comparables: list[ComparablePrice],
    valuation_mode: str = "market",
    enough_evidence: bool = True
) -> dict:
    """
    A-Rank V1 真实资产基础估值。

    market：

        Comparable
            ↓
        Relevance Filter
            ↓
        MAD
            ↓
        Median
            ↓
        Market Value


    model：

        V1 暂时同样使用 Comparable Proxy，

        但 Confidence 更保守。


    注意：

    这里计算的是：

        完整市场 Anchor 的价值。


    如果物品存在 Experience Overlay：

    这里的结果还不是最终 A-Rank Value。

    后续必须再调用：

        calculate_experience_overlay_valuation()
    """

    if valuation_mode not in {
        "market",
        "model",
    }:

        raise ValueError(
            "calculate_market_valuation "
            "只支持 market 或 model。"
        )

    # ========================================================
    # 清理 Comparable
    # ========================================================

    cleaned = remove_outliers(
        comparables
    )

    if not cleaned:

        raise ValueError(
            "没有足够的有效市场价格。"
        )

    prices = sorted(
        item.price_cny
        for item in cleaned
    )

    # ========================================================
    # Median = Best Estimate
    # ========================================================

    best_estimate = (
        statistics.median(
            prices
        )
    )

    low_estimate = min(
        prices
    )

    high_estimate = max(
        prices
    )

    # ========================================================
    # Confidence
    # ========================================================

    confidence = calculate_confidence(

        cleaned,

        valuation_mode=(
            valuation_mode
        ),

        enough_evidence=(
            enough_evidence
        ),
    )

    # ========================================================
    # A-Rank
    # ========================================================

    a_rank = calculate_a_rank(
        best_estimate
    )

    # ========================================================
    # Representative Comparable
    # ========================================================

    representative_comparable = (
        select_representative_comparable(
            cleaned,
            best_estimate,
        )
    )

    # ========================================================
    # Method
    # ========================================================

    if valuation_mode == "market":

        valuation_method = (
            "comparable_median_v1"
        )

    else:

        valuation_method = (
            "model_comparable_proxy_v1"
        )

    return {

        "best_estimate":
            round(
                best_estimate,
                2,
            ),

        "low_estimate":
            round(
                low_estimate,
                2,
            ),

        "high_estimate":
            round(
                high_estimate,
                2,
            ),

        "confidence":
            confidence,

        "a_rank":
            a_rank,

        "comparables_used":
            cleaned,

        "representative_comparable":
            representative_comparable,

        "valuation_mode":
            valuation_mode,

        "valuation_method":
            valuation_method,
    }


# ============================================================
# 7. Experience Overlay Confidence
# ============================================================

def calculate_experience_confidence(
    market_confidence: int,
    applicable: bool
) -> int:
    """
    Experience Overlay 会引入明显的主观判断。

    因此：

    普通市场 Confidence

    不能原封不动地作为最终体验估值 Confidence。


    V1：

    Overlay 不适用：
        上限 80

    Overlay 适用：
        上限 70


    这不是统计意义上的概率，

    只是：

    A-Rank 对当前估值证据强度的产品化表达。
    """

    if applicable:

        maximum = 70

    else:

        maximum = 80

    return max(
        0,
        min(
            market_confidence,
            maximum,
        )
    )


# ============================================================
# 8. Experience Overlay Valuation
# ============================================================

def calculate_experience_overlay_valuation(
    anchor_valuation: dict,
    overlay: ExperienceOverlayResult
) -> dict:
    """
    将：

        完整市场 Anchor

    转换为：

        特定部分 / 特定情境
        的最终 A-Rank Value。


    ========================================================
    核心公式
    ========================================================

    P = 完整市场 Anchor 价值

    m = material_fraction

    e = experience_share

    c = context_intensity


    Material Value：

        P × m


    Experience Premium：

        P × e × c


    Final A-Rank Value：

        Material Value
        +
        Experience Premium


    ========================================================
    示例
    ========================================================

    整瓶冰可乐：

        P = ¥3.50


    第一口：

        m = 0.08

        e = 0.45

        c = 1.0


    Material：

        3.50 × 0.08
        = ¥0.28


    Experience：

        3.50 × 0.45 × 1
        = ¥1.575


    Final：

        ¥1.855


    ========================================================
    重要
    ========================================================

    AI 只能生成：

        m
        e
        c

    所有人民币金额：

        全部由这里的 Python 计算。
    """

    # ========================================================
    # Anchor
    # ========================================================

    anchor_best = float(
        anchor_valuation[
            "best_estimate"
        ]
    )

    anchor_low = float(
        anchor_valuation[
            "low_estimate"
        ]
    )

    anchor_high = float(
        anchor_valuation[
            "high_estimate"
        ]
    )

    if anchor_best <= 0:

        raise ValueError(
            "Experience Overlay 的市场 Anchor "
            "必须大于 0。"
        )

    # ========================================================
    # Clamp
    #
    # Schema 已经限制范围，
    # Python 再保险一次。
    # ========================================================

    material_fraction = max(
        0.0,
        min(
            float(
                overlay.material_fraction
            ),
            1.0,
        ),
    )

    experience_share = max(
        0.0,
        min(
            float(
                overlay.experience_share
            ),
            1.0,
        ),
    )

    context_intensity = max(
        0.0,
        min(
            float(
                overlay.context_intensity
            ),
            2.0,
        ),
    )

    # ========================================================
    # Overlay 不适用
    #
    # 体验价值归零。
    #
    # 但是：
    #
    # material_fraction 仍然必须保留。
    #
    # 因为：
    #
    # “第一口可乐”
    #
    # 即使没有体验溢价，
    # 也不能突然变成整瓶可乐的价格。
    # ========================================================

    if not overlay.applicable:

        experience_share = 0.0
        context_intensity = 0.0

    # ========================================================
    # Material Value
    # ========================================================

    material_value = (
        anchor_best
        * material_fraction
    )

    material_low = (
        anchor_low
        * material_fraction
    )

    material_high = (
        anchor_high
        * material_fraction
    )

    # ========================================================
    # Raw Experience Premium
    # ========================================================

    raw_experience_premium = (
        anchor_best
        * experience_share
        * context_intensity
    )

    raw_experience_low = (
        anchor_low
        * experience_share
        * context_intensity
    )

    raw_experience_high = (
        anchor_high
        * experience_share
        * context_intensity
    )

    # ========================================================
    # Experience Premium Safety Cap
    # ========================================================

    premium_cap_best = (
        anchor_best
        * MAX_EXPERIENCE_PREMIUM_MULTIPLIER
    )

    premium_cap_low = (
        anchor_low
        * MAX_EXPERIENCE_PREMIUM_MULTIPLIER
    )

    premium_cap_high = (
        anchor_high
        * MAX_EXPERIENCE_PREMIUM_MULTIPLIER
    )

    experience_premium = min(
        raw_experience_premium,
        premium_cap_best,
    )

    experience_low = min(
        raw_experience_low,
        premium_cap_low,
    )

    experience_high = min(
        raw_experience_high,
        premium_cap_high,
    )

    # ========================================================
    # Final Value
    # ========================================================

    final_best = (
        material_value
        + experience_premium
    )

    final_low = (
        material_low
        + experience_low
    )

    final_high = (
        material_high
        + experience_high
    )

    # 防止极端情况下最终值变成 0
    final_best = max(
        final_best,
        0.01,
    )

    final_low = max(
        final_low,
        0.01,
    )

    final_high = max(
        final_high,
        final_low,
    )

    # ========================================================
    # A-Rank
    # ========================================================

    a_rank = calculate_a_rank(
        final_best
    )

    # ========================================================
    # Experience Multiplier
    #
    # 最终价值相当于完整 Anchor 的多少倍。
    #
    # 例如：
    #
    # 0.08 + 0.45 * 1
    # = 0.53
    #
    # 表示：
    #
    # 第一口虽然只占 8% 物质量，
    # 但最终 A-Rank Value
    # 相当于整瓶商品价格的 53%。
    # ========================================================

    experience_multiplier = (
        final_best
        / anchor_best
    )

    # ========================================================
    # Premium vs Material
    #
    # 例如：
    #
    # 一张厕纸：
    #
    # material = ¥0.02
    # premium = ¥1.50
    #
    # premium/material
    # 可能达到几十倍。
    #
    # 这个数据非常适合以后 UI 展示。
    # ========================================================

    if material_value > 0:

        premium_vs_material = (
            experience_premium
            / material_value
        )

    else:

        premium_vs_material = None

    # ========================================================
    # Confidence
    # ========================================================

    market_confidence = int(
        anchor_valuation.get(
            "confidence",
            0,
        )
    )

    confidence = (
        calculate_experience_confidence(

            market_confidence=(
                market_confidence
            ),

            applicable=(
                overlay.applicable
            ),
        )
    )

    # ========================================================
    # Result
    # ========================================================

    return {

        # ----------------------------------------------------
        # Final A-Rank Value
        # ----------------------------------------------------

        "best_estimate":
            round(
                final_best,
                2,
            ),

        "low_estimate":
            round(
                final_low,
                2,
            ),

        "high_estimate":
            round(
                final_high,
                2,
            ),

        "a_rank":
            a_rank,

        "confidence":
            confidence,

        # ----------------------------------------------------
        # Anchor
        # ----------------------------------------------------

        "anchor_best_estimate":
            round(
                anchor_best,
                2,
            ),

        "anchor_low_estimate":
            round(
                anchor_low,
                2,
            ),

        "anchor_high_estimate":
            round(
                anchor_high,
                2,
            ),

        "anchor_description":
            overlay
            .anchor_description,

        "market_confidence":
            market_confidence,

        # ----------------------------------------------------
        # Material Component
        # ----------------------------------------------------

        "material_fraction":
            round(
                material_fraction,
                4,
            ),

        "material_value":
            round(
                material_value,
                2,
            ),

        # ----------------------------------------------------
        # Experience Component
        # ----------------------------------------------------

        "experience_overlay":
            bool(
                overlay.applicable
            ),

        "experience_share":
            round(
                experience_share,
                4,
            ),

        "context_intensity":
            round(
                context_intensity,
                4,
            ),

        "experience_premium":
            round(
                experience_premium,
                2,
            ),

        "premium_label":
            overlay
            .premium_label,

        # ----------------------------------------------------
        # Diagnostic / Product Metrics
        # ----------------------------------------------------

        "experience_multiplier":
            round(
                experience_multiplier,
                4,
            ),

        "premium_vs_material":
            (
                round(
                    premium_vs_material,
                    2,
                )
                if premium_vs_material
                is not None
                else None
            ),

        # ----------------------------------------------------
        # AI Experience Explanation
        # ----------------------------------------------------

        "signature_detail":
            overlay
            .signature_detail,

        "experience_factors":
            overlay
            .factors,

        "experience_rationale":
            overlay
            .rationale,

        "experience_commentary":
            overlay
            .commentary,

        # ----------------------------------------------------
        # Market Information
        # ----------------------------------------------------

        "comparables_used":
            anchor_valuation.get(
                "comparables_used",
                [],
            ),

        "representative_comparable":
            anchor_valuation.get(
                "representative_comparable"
            ),

        "valuation_mode":
            anchor_valuation.get(
                "valuation_mode",
                "market",
            ),

        "valuation_method":
            "experience_overlay_v1",
    }


# ============================================================
# 9. Real Asset Valuation Alias
# ============================================================

def calculate_real_asset_valuation(
    comparables: list[ComparablePrice],
    valuation_mode: str = "market",
    enough_evidence: bool = True
) -> dict:
    """
    market / model 的统一入口。

    注意：

    这里返回的是：

        基础市场 Anchor Value。

    如果：

        experience_overlay == True

    App 必须进一步调用：

        calculate_experience_overlay_valuation()
    """

    return calculate_market_valuation(

        comparables=(
            comparables
        ),

        valuation_mode=(
            valuation_mode
        ),

        enough_evidence=(
            enough_evidence
        ),
    )