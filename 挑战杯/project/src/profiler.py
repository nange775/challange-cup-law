"""人员画像模块 — 汇聚所有分析结果生成综合画像"""
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import get_person_transactions, get_bank_cards, get_all_persons, get_counterpart_summary
from src.anomaly import run_all_detections, get_risk_summary
from src.graph_analysis import build_transaction_graph, get_network_metrics, find_bridge_accounts, get_top_counterparts


def generate_profile(user_id: str) -> dict:
    """
    生成目标人员的完整画像报告。
    聚合: 基础信息 + 交易统计 + 异常检测 + 关系网络分析
    """
    persons = get_all_persons()
    person_row = persons[persons["user_id"] == user_id]
    if person_row.empty:
        return {"error": f"未找到用户 {user_id}"}

    person = person_row.iloc[0].to_dict()
    cards = get_bank_cards(user_id)
    tx = get_person_transactions(user_id)

    if tx.empty:
        return {"person": person, "cards": cards.to_dict("records"), "error": "无交易数据"}

    # === 基础交易统计 ===
    income = tx[tx["direction"] == "入"]
    expense = tx[tx["direction"] == "出"]

    basic_stats = {
        "total_tx": len(tx),
        "date_range": f"{tx['trade_time'].min().strftime('%Y-%m-%d')} 至 {tx['trade_time'].max().strftime('%Y-%m-%d')}",
        "total_income_yuan": income["amount"].sum() / 100 if not income.empty else 0,
        "total_expense_yuan": expense["amount"].sum() / 100 if not expense.empty else 0,
        "avg_monthly_income_yuan": 0,
        "avg_monthly_expense_yuan": 0,
        "max_single_income_yuan": income["amount"].max() / 100 if not income.empty else 0,
        "max_single_expense_yuan": expense["amount"].max() / 100 if not expense.empty else 0,
    }

    # 月均
    n_months = tx["trade_time"].dt.to_period("M").nunique()
    if n_months > 0:
        basic_stats["avg_monthly_income_yuan"] = basic_stats["total_income_yuan"] / n_months
        basic_stats["avg_monthly_expense_yuan"] = basic_stats["total_expense_yuan"] / n_months

    # === 交易用途分布 ===
    purpose_dist = tx.groupby("purpose").agg(
        count=("amount", "count"),
        total_yuan=("amount", lambda x: x.sum() / 100)
    ).reset_index().sort_values("count", ascending=False).to_dict("records")

    # === 交易时段分布 ===
    tx_copy = tx.copy()
    tx_copy["hour"] = tx_copy["trade_time"].dt.hour
    hour_dist = tx_copy.groupby("hour").size().to_dict()

    # === 异常检测 ===
    anomaly_results = run_all_detections(tx)
    risk_items = get_risk_summary(anomaly_results)

    # === 关系网络 ===
    G = build_transaction_graph(tx)
    target_name = person.get("name", user_id)
    network_metrics = get_network_metrics(G, target_name)
    bridges = find_bridge_accounts(G, target_name)
    top_contacts = get_top_counterparts(G, target_name, top_n=15)

    # === 对手方汇总 ===
    counterpart_summary = get_counterpart_summary(user_id)

    # === 综合风险评级 ===
    high_count = sum(1 for r in risk_items if r["risk_level"] == "HIGH")
    medium_count = sum(1 for r in risk_items if r["risk_level"] == "MEDIUM")
    if high_count >= 3:
        overall_risk = "HIGH"
    elif high_count >= 1 or medium_count >= 3:
        overall_risk = "MEDIUM"
    else:
        overall_risk = "LOW"

    return {
        "person": person,
        "cards": cards.to_dict("records"),
        "basic_stats": basic_stats,
        "purpose_distribution": purpose_dist,
        "hour_distribution": hour_dist,
        "anomaly_results": {
            k: v.to_dict("records") if isinstance(v, pd.DataFrame) and not v.empty else []
            for k, v in anomaly_results.items()
        },
        "risk_items": risk_items,
        "overall_risk": overall_risk,
        "network_metrics": network_metrics,
        "bridge_accounts": bridges,
        "top_contacts": top_contacts,
        "counterpart_summary": counterpart_summary.to_dict("records") if not counterpart_summary.empty else [],
    }


def generate_report_text(profile: dict) -> str:
    """将画像数据转为结构化文本报告"""
    if "error" in profile and "person" not in profile:
        return f"错误: {profile['error']}"

    person = profile["person"]
    stats = profile.get("basic_stats", {})
    lines = []

    lines.append("=" * 60)
    lines.append("检察侦查(资金拓扑)画像报告")
    lines.append("=" * 60)

    # 一、基本信息
    lines.append("\n一、嫌疑人基本信息")
    lines.append(f"  姓名: {person.get('name', '未知')}")
    lines.append(f"  身份证号: {person.get('id_card', '未知')}")
    lines.append(f"  财付通账号: {person.get('user_id', '未知')}")
    lines.append(f"  绑定手机: {person.get('phone', '未知')}")
    cards = profile.get("cards", [])
    if cards:
        lines.append(f"  关联银行卡: {len(cards)}张")
        for c in cards:
            lines.append(f"    - {c.get('bank_name', '')} {c.get('card_no', '')} ({c.get('status', '')})")

    # 二、资金概况
    lines.append(f"\n二、资金流水概况")
    lines.append(f"  统计区间: {stats.get('date_range', '')}")
    lines.append(f"  交易总笔数: {stats.get('total_tx', 0)}")
    lines.append(f"  总入账: {stats.get('total_income_yuan', 0):,.0f} 元")
    lines.append(f"  总出账: {stats.get('total_expense_yuan', 0):,.0f} 元")
    lines.append(f"  月均入账: {stats.get('avg_monthly_income_yuan', 0):,.0f} 元")
    lines.append(f"  月均出账: {stats.get('avg_monthly_expense_yuan', 0):,.0f} 元")
    lines.append(f"  最大单笔入账: {stats.get('max_single_income_yuan', 0):,.0f} 元")
    lines.append(f"  最大单笔出账: {stats.get('max_single_expense_yuan', 0):,.0f} 元")

    # 三、风险预警
    risk_items = profile.get("risk_items", [])
    overall = profile.get("overall_risk", "LOW")
    lines.append(f"\n三、风险预警 (综合评级: {overall})")
    if risk_items:
        for i, item in enumerate(risk_items, 1):
            lines.append(f"  [{item['risk_level']}] {i}. [{item['type']}] {item['description']}")
    else:
        lines.append("  未发现明显异常。")

    # 四、关键关系人
    top_contacts = profile.get("top_contacts", [])
    lines.append(f"\n四、关键关系人 (资金往来TOP)")
    if top_contacts:
        for i, c in enumerate(top_contacts[:10], 1):
            lines.append(
                f"  {i}. {c['name']}: 入账{c['in']:,.0f}元, 出账{c['out']:,.0f}元, 共{c['count']}笔"
            )

    # 五、疑似过桥账户
    bridges = profile.get("bridge_accounts", [])
    if bridges:
        lines.append(f"\n五、疑似过桥账户(白手套)")
        for b in bridges[:5]:
            ds = b.get("downstream", b.get("upstream", []))
            lines.append(
                f"  - {b['bridge_name']}({b['direction']}): "
                f"流入{b['flow_in']:,.0f}元/流出{b['flow_out']:,.0f}元, "
                f"关联: {', '.join(str(d) for d in ds)}"
            )

    # 六、侦查建议
    lines.append(f"\n六、侦查建议")
    suggestions = _generate_suggestions(profile)
    for i, s in enumerate(suggestions, 1):
        lines.append(f"  {i}. {s}")

    lines.append("\n" + "=" * 60)
    lines.append("本报告基于财付通资金流水数据自动生成, 仅供侦查参考。")
    lines.append("报告中涉及的异常标记需结合案件实际情况进一步核实。")
    lines.append("=" * 60)

    return "\n".join(lines)


def _generate_suggestions(profile: dict) -> list:
    """基于画像结果生成侦查建议"""
    suggestions = []
    risk_items = profile.get("risk_items", [])
    bridges = profile.get("bridge_accounts", [])

    for item in risk_items:
        if item["type"] == "财富突增":
            suggestions.append(
                f"建议调取嫌疑人在{item['description'].split('最高为')[1].split('(')[0] if '最高为' in item['description'] else '异常月份'}"
                f"期间经手的案件卷宗, 核查是否存在与入账时间吻合的案件处理行为。"
            )
        elif item["type"] == "高频对手方":
            name = item["description"].split("「")[1].split("」")[0] if "「" in item["description"] else "相关人员"
            suggestions.append(f"建议调查「{name}」的真实身份及其与嫌疑人的社会关系, 核实转账的合法事由。")
        elif item["type"] == "深夜异常交易":
            suggestions.append("建议重点关注深夜时段的大额交易, 核查对手方身份及交易背景。")
        elif item["type"] == "化整为零":
            suggestions.append("发现疑似化整为零操作, 建议合并分析同一对手方的系列小额交易。")

    if bridges:
        for b in bridges[:2]:
            suggestions.append(
                f"「{b['bridge_name']}」疑似过桥账户, 建议调取其完整流水数据进行穿透分析。"
            )

    if not suggestions:
        suggestions.append("当前数据未发现明显高风险特征, 建议扩大数据采集范围(如银行流水、房产信息)进一步排查。")

    return suggestions
