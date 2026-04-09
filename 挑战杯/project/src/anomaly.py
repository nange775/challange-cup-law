"""核心异常检测算法模块"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    STRUCTURING_WINDOW_MINUTES, STRUCTURING_MIN_COUNT,
    ABNORMAL_HOUR_START, ABNORMAL_HOUR_END,
    WEALTH_SURGE_THRESHOLD, HIGH_FREQ_COUNTERPART_THRESHOLD,
    LARGE_AMOUNT_THRESHOLD,
)


def detect_structuring(df: pd.DataFrame) -> pd.DataFrame:
    """
    化整为零检测：在指定时间窗口内，同一对手方的多笔小额交易合计为整数金额。
    典型行贿手法：将大额拆分为多笔小额转账以逃避监控。

    返回 DataFrame: counterpart_name, tx_count, total_yuan, time_start, time_end, trade_nos
    """
    if df.empty:
        return pd.DataFrame()

    results = []
    df_sorted = df.sort_values("trade_time")

    # 按对手方+方向分组
    for (cp, direction), group in df_sorted.groupby(["counterpart_name", "direction"]):
        if not cp or cp == "":
            continue
        group = group.sort_values("trade_time").reset_index(drop=True)
        n = len(group)
        i = 0
        while i < n:
            j = i + 1
            window_end = group.iloc[i]["trade_time"] + pd.Timedelta(minutes=STRUCTURING_WINDOW_MINUTES)
            while j < n and group.iloc[j]["trade_time"] <= window_end:
                j += 1
            window = group.iloc[i:j]
            if len(window) >= STRUCTURING_MIN_COUNT:
                total = window["amount"].sum()
                total_yuan = total / 100
                # 判断是否为整数金额(元为单位,百元整数倍)
                if total_yuan >= 100 and total_yuan % 100 == 0:
                    results.append({
                        "counterpart_name": cp,
                        "direction": direction,
                        "tx_count": len(window),
                        "total_yuan": total_yuan,
                        "time_start": window.iloc[0]["trade_time"],
                        "time_end": window.iloc[-1]["trade_time"],
                        "trade_nos": ",".join(window["trade_no"].astype(str).tolist()),
                        "risk_level": "HIGH" if total_yuan >= 5000 else "MEDIUM",
                    })
            i = j if j > i + 1 else i + 1

    return pd.DataFrame(results)


def detect_abnormal_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    异常时段交易检测：深夜(0:00-6:00)的交易，尤其是大额转账。
    司法人员受贿往往选择深夜进行以避人耳目。

    返回异常时段交易记录(附加风险标签)。
    """
    if df.empty:
        return pd.DataFrame()

    df_copy = df.copy()
    df_copy["hour"] = df_copy["trade_time"].dt.hour
    abnormal = df_copy[
        (df_copy["hour"] >= ABNORMAL_HOUR_START) &
        (df_copy["hour"] < ABNORMAL_HOUR_END)
    ].copy()

    if abnormal.empty:
        return pd.DataFrame()

    abnormal["risk_level"] = abnormal["amount"].apply(
        lambda x: "HIGH" if x >= LARGE_AMOUNT_THRESHOLD else "MEDIUM"
    )
    return abnormal.sort_values("trade_time")


def detect_wealth_surge(df: pd.DataFrame) -> pd.DataFrame:
    """
    财富突增检测：某月入账金额远超月平均水平。
    反映可能存在突然的非法收入来源。

    返回 DataFrame: month, income_yuan, avg_income_yuan, ratio, risk_level
    """
    if df.empty:
        return pd.DataFrame()

    income = df[df["direction"] == "入"].copy()
    if income.empty:
        return pd.DataFrame()

    income["month"] = income["trade_time"].dt.to_period("M")
    monthly = income.groupby("month")["amount"].sum().reset_index()
    monthly.columns = ["month", "income"]
    monthly["income_yuan"] = monthly["income"] / 100

    avg_income = monthly["income_yuan"].mean()
    if avg_income == 0:
        return pd.DataFrame()

    monthly["avg_income_yuan"] = avg_income
    monthly["ratio"] = monthly["income_yuan"] / avg_income
    surge = monthly[monthly["ratio"] >= WEALTH_SURGE_THRESHOLD].copy()
    surge["risk_level"] = surge["ratio"].apply(
        lambda x: "HIGH" if x >= 3.0 else "MEDIUM"
    )
    surge["month"] = surge["month"].astype(str)
    return surge.sort_values("ratio", ascending=False)


def detect_high_freq_counterpart(df: pd.DataFrame) -> pd.DataFrame:
    """
    高频对手方检测：与某个自然人的月均交易频次异常高。
    过高的个人间转账频率可能指向利益输送。

    返回 DataFrame: counterpart_name, total_count, monthly_avg, total_in_yuan, total_out_yuan, risk_level
    """
    if df.empty:
        return pd.DataFrame()

    # 只看与自然人的交易(排除企业/机构)
    person_tx = df[
        (df["counterpart_name"].str.len() <= 4) &
        (df["counterpart_name"].str.len() > 0) &
        (~df["counterpart_name"].str.contains("公司|有限|银联|财付通|科技|管理|股份", na=False))
    ].copy()

    if person_tx.empty:
        return pd.DataFrame()

    person_tx["month"] = person_tx["trade_time"].dt.to_period("M")
    n_months = person_tx["month"].nunique()
    if n_months == 0:
        return pd.DataFrame()

    summary = person_tx.groupby("counterpart_name").agg(
        total_count=("amount", "count"),
        total_in=("amount", lambda x: x[person_tx.loc[x.index, "direction"] == "入"].sum()),
        total_out=("amount", lambda x: x[person_tx.loc[x.index, "direction"] == "出"].sum()),
    ).reset_index()

    summary["monthly_avg"] = (summary["total_count"] / n_months).round(1)
    summary["total_in_yuan"] = summary["total_in"] / 100
    summary["total_out_yuan"] = summary["total_out"] / 100
    summary = summary[summary["monthly_avg"] >= HIGH_FREQ_COUNTERPART_THRESHOLD]
    summary["risk_level"] = summary["monthly_avg"].apply(
        lambda x: "HIGH" if x >= 50 else "MEDIUM"
    )
    return summary.sort_values("monthly_avg", ascending=False)


def detect_large_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """
    大额转账检测：单笔金额超过阈值的个人间转账。
    """
    if df.empty:
        return pd.DataFrame()

    large = df[
        (df["amount"] >= LARGE_AMOUNT_THRESHOLD) &
        (df["purpose"].str.contains("转账", na=False))
    ].copy()

    if large.empty:
        return pd.DataFrame()

    large["amount_yuan"] = large["amount"] / 100
    large["risk_level"] = large["amount"].apply(
        lambda x: "HIGH" if x >= 1000000 else "MEDIUM"  # 1万元以上
    )
    return large.sort_values("amount", ascending=False)


def detect_round_amount_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """
    整数金额模式检测：频繁出现的整百/整千元转账。
    行贿受贿金额通常为整数。
    """
    if df.empty:
        return pd.DataFrame()

    transfers = df[df["purpose"].str.contains("转账", na=False)].copy()
    if transfers.empty:
        return pd.DataFrame()

    transfers["amount_yuan"] = transfers["amount"] / 100
    # 筛选整百元且>=500元的转账
    round_tx = transfers[
        (transfers["amount_yuan"] >= 500) &
        (transfers["amount_yuan"] % 100 == 0)
    ].copy()

    if round_tx.empty:
        return pd.DataFrame()

    round_tx["risk_level"] = round_tx["amount_yuan"].apply(
        lambda x: "HIGH" if x >= 5000 else "MEDIUM"
    )
    return round_tx.sort_values("amount", ascending=False)


def run_all_detections(df: pd.DataFrame) -> dict:
    """运行所有异常检测算法，返回结果字典"""
    return {
        "structuring": detect_structuring(df),
        "abnormal_time": detect_abnormal_time(df),
        "wealth_surge": detect_wealth_surge(df),
        "high_freq_counterpart": detect_high_freq_counterpart(df),
        "large_transfers": detect_large_transfers(df),
        "round_amount": detect_round_amount_pattern(df),
    }


def get_risk_summary(results: dict) -> list:
    """汇总所有检测结果为风险摘要列表"""
    summary = []

    structuring = results.get("structuring")
    if structuring is not None and not structuring.empty:
        for _, row in structuring.iterrows():
            summary.append({
                "type": "化整为零",
                "risk_level": row["risk_level"],
                "description": (
                    f"与「{row['counterpart_name']}」在{row['time_start']}至{row['time_end']}期间"
                    f"存在{row['tx_count']}笔{row['direction']}账交易, 合计{row['total_yuan']:.0f}元(整数金额)"
                ),
            })

    abnormal_time = results.get("abnormal_time")
    if abnormal_time is not None and not abnormal_time.empty:
        high_risk = abnormal_time[abnormal_time["risk_level"] == "HIGH"]
        summary.append({
            "type": "深夜异常交易",
            "risk_level": "HIGH" if len(high_risk) > 0 else "MEDIUM",
            "description": (
                f"共发现{len(abnormal_time)}笔深夜(0:00-6:00)交易, "
                f"其中{len(high_risk)}笔为大额交易"
            ),
        })

    surge = results.get("wealth_surge")
    if surge is not None and not surge.empty:
        top = surge.iloc[0]
        summary.append({
            "type": "财富突增",
            "risk_level": top["risk_level"],
            "description": (
                f"共{len(surge)}个月份入账异常, 最高为{top['month']}"
                f"(入账{top['income_yuan']:.0f}元, 是月均的{top['ratio']:.1f}倍)"
            ),
        })

    hf = results.get("high_freq_counterpart")
    if hf is not None and not hf.empty:
        for _, row in hf.iterrows():
            summary.append({
                "type": "高频对手方",
                "risk_level": row["risk_level"],
                "description": (
                    f"与「{row['counterpart_name']}」月均交易{row['monthly_avg']}笔, "
                    f"总计入账{row['total_in_yuan']:.0f}元/出账{row['total_out_yuan']:.0f}元"
                ),
            })

    large = results.get("large_transfers")
    if large is not None and not large.empty:
        summary.append({
            "type": "大额转账",
            "risk_level": "HIGH",
            "description": f"共发现{len(large)}笔大额转账, 最大单笔{large.iloc[0]['amount_yuan']:.0f}元",
        })

    return sorted(summary, key=lambda x: 0 if x["risk_level"] == "HIGH" else 1)
