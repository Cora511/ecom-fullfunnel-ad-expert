#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全域投放测算脚本 —— 保本 ROI / 目标 ROI / 可承受 CPC / 预算拆分 / 指标计算

用于替代口算，避免算术错误。所有结果为预估，以账户实际大盘数据为准。

用法示例：
  # 1. 保本线测算
  python3 roi_calc.py breakeven --gross-margin 0.45
  python3 roi_calc.py breakeven --gross-margin 0.45 --target-margin 0.20 \\
      --aov 199 --cvr 0.03

  # 2. 全域预算拆分
  python3 roi_calc.py budget --total 10000 --stage daily --decision long
  python3 roi_calc.py budget --total 10000 --stage coldstart

  # 3. 投放指标计算
  python3 roi_calc.py kpi --cost 5000 --revenue 12500 --impressions 500000 \\
      --clicks 8000 --orders 250 --add-to-cart 600

  # JSON 输出（便于程序化使用）
  python3 roi_calc.py breakeven --gross-margin 0.45 --json
"""

import argparse
import json
import sys


def pct(x):
    return f"{x * 100:.2f}%"


def money(x):
    return f"¥{x:,.2f}"


# ---------------------------------------------------------------- 保本测算

def calc_breakeven(gross_margin, target_margin=None, aov=None, cvr=None,
                   target_roi=None, cpc=None):
    if gross_margin <= 0 or gross_margin >= 1:
        raise ValueError("毛利率需在 (0, 1) 区间，例如 0.45 表示 45%")

    breakeven_roi = 1.0 / gross_margin
    out = {
        "毛利率": pct(gross_margin),
        "保本ROI": round(breakeven_roi, 2),
    }

    if target_margin is not None:
        out["目标利润率"] = pct(target_margin)
        out["目标ROI"] = round(breakeven_roi * (1 + target_margin), 2)

    effective_target = target_roi if target_roi else out.get("目标ROI", breakeven_roi)

    if aov is not None and cvr is not None:
        # 可承受 CPC = 客单价 × CVR ÷ 目标 ROI
        max_cpc = aov * cvr / effective_target
        out["客单价"] = money(aov)
        out["CVR"] = pct(cvr)
        out["测算用目标ROI"] = round(effective_target, 2)
        out["可承受CPC"] = money(max_cpc)

        if cpc is not None:
            out["当前CPC"] = money(cpc)
            out["CPC判定"] = "高于可承受上限，需优化" if cpc > max_cpc else "在可承受范围内"
            out["CPC差额"] = money(abs(cpc - max_cpc))

    if target_roi is not None:
        out["目标ROI"] = round(target_roi, 2)
        out["相对保本线"] = "达标" if target_roi >= breakeven_roi else "低于保本线，需调整"

    return out


# ---------------------------------------------------------------- 预算拆分

# 阶段基准比例：(乘风, 千川)
STAGE_RATIO = {
    "coldstart": (0.50, 0.50),   # 新品冷启动
    "daily": (0.35, 0.65),       # 日常稳投
    "promo": (0.30, 0.70),       # 大促放量
}

# 决策周期调整（对乘风的偏移量）
DECISION_SHIFT = {
    "long": 0.10,    # 决策周期长、客单高 → 乘风 +10pp
    "short": -0.05,  # 决策快、冲动型 → 千川 +5pp
    "none": 0.0,
}


def calc_budget(total, stage="daily", decision="none", promo_days=0):
    if stage not in STAGE_RATIO:
        raise ValueError(f"stage 需为 {list(STAGE_RATIO)} 之一")
    if decision not in DECISION_SHIFT:
        raise ValueError(f"decision 需为 {list(DECISION_SHIFT)} 之一")

    xhs_ratio, qc_ratio = STAGE_RATIO[stage]
    shift = DECISION_SHIFT[decision]
    xhs_ratio = min(max(xhs_ratio + shift, 0.20), 0.60)
    qc_ratio = 1 - xhs_ratio

    xhs = total * xhs_ratio
    qc = total * qc_ratio

    # 乘风内部拆分：笔记加热 60% / 搜索广告 40%
    # 千川内部拆分：短视频 45% / 直播 40% / 搜索 15%
    out = {
        "总预算": money(total),
        "阶段": stage,
        "决策周期调整": decision,
        "小红书乘风": {
            "占比": pct(xhs_ratio),
            "金额": money(xhs),
            "笔记加热": money(xhs * 0.60),
            "搜索广告": money(xhs * 0.40),
        },
        "巨量千川": {
            "占比": pct(qc_ratio),
            "金额": money(qc),
            "短视频": money(qc * 0.45),
            "直播": money(qc * 0.40),
            "搜索千川": money(qc * 0.15),
        },
    }

    if promo_days:
        out["大促周期总预算"] = money(total * promo_days)
        out["大促提示"] = "建议提前 3~5 天完成计划搭建与素材储备，保本 ROI 基准按成本上涨幅度上浮"

    out["说明"] = "比例为起点而非结论，需结合类目、客单价、保本 ROI 复核"
    return out


# ---------------------------------------------------------------- 指标计算

def calc_kpi(cost=None, revenue=None, impressions=None, clicks=None,
             orders=None, add_to_cart=None):
    out = {}

    if cost is not None and revenue is not None:
        out["消耗"] = money(cost)
        out["成交金额"] = money(revenue)
        out["ROI"] = round(revenue / cost, 2) if cost else None

    if impressions is not None and cost is not None:
        out["CPM"] = round(cost / impressions * 1000, 2)

    if clicks is not None and impressions is not None:
        out["CTR"] = pct(clicks / impressions) if impressions else None

    if clicks is not None and cost is not None:
        out["CPC"] = round(cost / clicks, 2)

    if orders is not None and clicks is not None:
        out["CVR"] = pct(orders / clicks) if clicks else None

    if orders is not None and cost is not None:
        out["千次成交成本"] = round(cost / orders * 1000, 2) if orders else None

    if add_to_cart is not None and cost is not None:
        out["加购成本"] = round(cost / add_to_cart, 2) if add_to_cart else None

    if orders is not None and add_to_cart is not None:
        out["加购转化率"] = pct(orders / add_to_cart) if add_to_cart else None

    return out


# ---------------------------------------------------------------- CLI

def render(data, as_json):
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for k, v in data.items():
        if isinstance(v, dict):
            print(f"{k}:")
            for kk, vv in v.items():
                print(f"  - {kk}: {vv}")
        else:
            print(f"{k}: {v}")


def main():
    parser = argparse.ArgumentParser(
        description="全域投放测算：保本ROI / 预算拆分 / 指标计算",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    sub = parser.add_subparsers(dest="command", required=True)

    # breakeven
    p1 = sub.add_parser("breakeven", help="保本 ROI / 目标 ROI / 可承受 CPC 测算")
    p1.add_argument("--gross-margin", type=float, required=True,
                    help="毛利率，小数形式，如 0.45 表示 45%")
    p1.add_argument("--target-margin", type=float, default=None,
                    help="目标利润率，如 0.20")
    p1.add_argument("--aov", type=float, default=None, help="客单价（元）")
    p1.add_argument("--cvr", type=float, default=None, help="转化率，如 0.03")
    p1.add_argument("--target-roi", type=float, default=None, help="直接指定目标 ROI")
    p1.add_argument("--cpc", type=float, default=None, help="当前 CPC，用于对比判定")

    # budget
    p2 = sub.add_parser("budget", help="全域预算拆分")
    p2.add_argument("--total", type=float, required=True, help="总预算（元）")
    p2.add_argument("--stage", default="daily",
                    choices=["coldstart", "daily", "promo"],
                    help="阶段：coldstart 冷启动 / daily 稳投 / promo 大促")
    p2.add_argument("--decision", default="none",
                    choices=["long", "short", "none"],
                    help="类目决策周期：long 长 / short 短 / none 默认")
    p2.add_argument("--promo-days", type=int, default=0, help="大促持续天数")

    # kpi
    p3 = sub.add_parser("kpi", help="投放指标计算")
    p3.add_argument("--cost", type=float, help="消耗（元）")
    p3.add_argument("--revenue", type=float, help="成交金额（元）")
    p3.add_argument("--impressions", type=float, help="曝光量")
    p3.add_argument("--clicks", type=float, help="点击量")
    p3.add_argument("--orders", type=float, help="成交订单数")
    p3.add_argument("--add-to-cart", type=float, dest="add_to_cart", help="加购数")

    args = parser.parse_args()

    try:
        if args.command == "breakeven":
            data = calc_breakeven(args.gross_margin, args.target_margin, args.aov,
                                  args.cvr, args.target_roi, args.cpc)
        elif args.command == "budget":
            data = calc_budget(args.total, args.stage, args.decision, args.promo_days)
        else:
            data = calc_kpi(args.cost, args.revenue, args.impressions,
                            args.clicks, args.orders, args.add_to_cart)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        sys.exit(1)

    render(data, args.json)
    if not args.json:
        print("\n以上为测算结果，属预估，以账户实际大盘数据为准。")


if __name__ == "__main__":
    main()
