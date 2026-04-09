"""交易分析与异常检测页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import init_db, get_all_persons, get_person_transactions
from src.anomaly import run_all_detections, get_risk_summary

init_db()


# 添加缓存装饰器以提升性能
@st.cache_data(ttl=300)
def compute_monthly_trend(tx_data: pd.DataFrame) -> pd.DataFrame:
    """计算月度趋势（带缓存）"""
    tx_copy = tx_data.copy()
    tx_copy["month"] = tx_copy["trade_time"].dt.to_period("M").astype(str)
    monthly = tx_copy.groupby(["month", "direction"])["amount"].sum().reset_index()
    monthly["amount_yuan"] = monthly["amount"] / 100
    return monthly


@st.cache_data(ttl=300)
def compute_hour_distribution(tx_data: pd.DataFrame) -> pd.DataFrame:
    """计算时段分布（带缓存）"""
    tx_copy = tx_data.copy()
    tx_copy["hour"] = tx_copy["trade_time"].dt.hour
    hour_dist = tx_copy.groupby("hour").size().reset_index(name="count")
    return hour_dist


@st.cache_data(ttl=300)
def compute_purpose_distribution(tx_data: pd.DataFrame) -> pd.DataFrame:
    """计算交易用途分布（带缓存）"""
    purpose_dist = tx_data.groupby("purpose").agg(
        count=("amount", "count"),
        total=("amount", "sum")
    ).reset_index()
    purpose_dist["total_yuan"] = purpose_dist["total"] / 100
    return purpose_dist


@st.cache_data(ttl=300)
def compute_top_counterparts(tx_data: pd.DataFrame) -> pd.DataFrame:
    """计算TOP对手方（带缓存）"""
    cp_summary = tx_data.groupby("counterpart_name").agg(
        tx_count=("amount", "count"),
        total_in=("amount", lambda x: x[tx_data.loc[x.index, "direction"] == "入"].sum() / 100),
        total_out=("amount", lambda x: x[tx_data.loc[x.index, "direction"] == "出"].sum() / 100),
    ).reset_index()
    cp_summary = cp_summary[cp_summary["counterpart_name"] != ""].nlargest(10, "tx_count")
    return cp_summary

st.title("交易分析与异常检测")

# 选择分析对象
persons = get_all_persons()
if persons.empty:
    st.warning("请先在「数据导入」页面导入数据。")
    st.stop()

options = {f"{row['name']}({row['user_id']})": row['user_id'] for _, row in persons.iterrows()}
selected = st.selectbox("选择分析对象", list(options.keys()))
user_id = options[selected]

tx = get_person_transactions(user_id)
if tx.empty:
    st.warning("该用户无交易数据。")
    st.stop()

# ==================== 基础统计 ====================
st.subheader("资金流水概况")

income = tx[tx["direction"] == "入"]
expense = tx[tx["direction"] == "出"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("交易总笔数", f"{len(tx):,}")
col2.metric("总入账", f"{income['amount'].sum()/100:,.0f} 元")
col3.metric("总出账", f"{expense['amount'].sum()/100:,.0f} 元")
col4.metric("时间跨度", f"{tx['trade_time'].min().strftime('%Y.%m')} - {tx['trade_time'].max().strftime('%Y.%m')}")

# ==================== 图表 ====================
tab_overview, tab_anomaly = st.tabs(["交易概览", "异常检测"])

with tab_overview:
    # 月度交易趋势（使用缓存）
    st.markdown("#### 月度资金流入/流出趋势")
    with st.spinner("加载月度趋势..."):
        monthly = compute_monthly_trend(tx)
        fig_monthly = px.bar(
            monthly, x="month", y="amount_yuan", color="direction",
            barmode="group", labels={"amount_yuan": "金额(元)", "month": "月份", "direction": "方向"},
            color_discrete_map={"入": "#2ecc71", "出": "#e74c3c"},
        )
        fig_monthly.update_layout(height=400)
        st.plotly_chart(fig_monthly, use_container_width=True, key="monthly_trend")

    # 交易用途分布
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 交易用途分布")
        with st.spinner("加载用途分布..."):
            purpose_dist = compute_purpose_distribution(tx)
            fig_purpose = px.pie(purpose_dist, names="purpose", values="count", hole=0.4)
            fig_purpose.update_layout(height=350)
            st.plotly_chart(fig_purpose, use_container_width=True, key="purpose_dist")

    with col_b:
        st.markdown("#### 交易时段分布")
        with st.spinner("加载时段分布..."):
            hour_dist = compute_hour_distribution(tx)
            fig_hour = px.bar(hour_dist, x="hour", y="count",
                             labels={"hour": "小时(0-23)", "count": "交易笔数"})
            fig_hour.update_layout(height=350)
            # 标记深夜区域
            fig_hour.add_vrect(x0=-0.5, x1=5.5, fillcolor="red", opacity=0.1,
                              annotation_text="深夜时段", annotation_position="top left")
            st.plotly_chart(fig_hour, use_container_width=True, key="hour_dist")

    # 对手方 TOP 10（使用缓存）
    st.markdown("#### 资金往来 TOP 10 对手方")
    with st.spinner("加载TOP对手方..."):
        cp_summary = compute_top_counterparts(tx)
        fig_cp = go.Figure()
        fig_cp.add_trace(go.Bar(name="入账(元)", x=cp_summary["counterpart_name"], y=cp_summary["total_in"], marker_color="#2ecc71"))
        fig_cp.add_trace(go.Bar(name="出账(元)", x=cp_summary["counterpart_name"], y=cp_summary["total_out"], marker_color="#e74c3c"))
        fig_cp.update_layout(barmode="group", height=400)
        st.plotly_chart(fig_cp, use_container_width=True, key="top_counterparts")


with tab_anomaly:
    st.markdown("#### 异常检测结果")

    with st.spinner("正在运行异常检测算法..."):
        results = run_all_detections(tx)
        risk_items = get_risk_summary(results)

    if not risk_items:
        st.info("未检测到明显异常。")
    else:
        # 风险摘要
        for item in risk_items:
            if item["risk_level"] == "HIGH":
                st.error(f"**[{item['type']}]** {item['description']}")
            else:
                st.warning(f"**[{item['type']}]** {item['description']}")

    st.divider()

    # 各检测详情
    st.markdown("##### 化整为零检测")
    structuring = results.get("structuring")
    if structuring is not None and not structuring.empty:
        st.dataframe(structuring, use_container_width=True, hide_index=True)
    else:
        st.caption("未发现化整为零模式。")

    st.markdown("##### 财富突增检测")
    surge = results.get("wealth_surge")
    if surge is not None and not surge.empty:
        fig_surge = px.bar(surge, x="month", y="income_yuan",
                          color="risk_level", color_discrete_map={"HIGH": "#e74c3c", "MEDIUM": "#f39c12"},
                          labels={"income_yuan": "入账(元)", "month": "月份"})
        fig_surge.add_hline(y=surge["avg_income_yuan"].iloc[0], line_dash="dash",
                           annotation_text=f"月均: {surge['avg_income_yuan'].iloc[0]:.0f}元")
        st.plotly_chart(fig_surge, use_container_width=True)
    else:
        st.caption("未发现财富突增。")

    st.markdown("##### 深夜异常交易")
    abnormal_time = results.get("abnormal_time")
    if abnormal_time is not None and not abnormal_time.empty:
        display_cols = ["trade_time", "direction", "purpose", "amount_yuan", "counterpart_name", "risk_level"]
        available_cols = [c for c in display_cols if c in abnormal_time.columns]
        st.dataframe(abnormal_time[available_cols].head(50), use_container_width=True, hide_index=True)
    else:
        st.caption("未发现深夜异常交易。")

    st.markdown("##### 大额转账")
    large = results.get("large_transfers")
    if large is not None and not large.empty:
        display_cols = ["trade_time", "direction", "amount_yuan", "counterpart_name", "risk_level"]
        available_cols = [c for c in display_cols if c in large.columns]
        st.dataframe(large[available_cols].head(50), use_container_width=True, hide_index=True)
    else:
        st.caption("未发现大额转账。")

    st.markdown("##### 高频对手方")
    hf = results.get("high_freq_counterpart")
    if hf is not None and not hf.empty:
        st.dataframe(hf, use_container_width=True, hide_index=True)
    else:
        st.caption("未发现异常高频对手方。")
