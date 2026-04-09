"""人员画像页面"""
import streamlit as st
import plotly.express as px
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import init_db, get_all_persons
from src.profiler import generate_profile, generate_report_text

init_db()

st.title("人员画像报告")

persons = get_all_persons()
if persons.empty:
    st.warning("请先在「数据导入」页面导入数据。")
    st.stop()

options = {f"{row['name']}({row['user_id']})": row['user_id'] for _, row in persons.iterrows()}
selected = st.selectbox("选择分析对象", list(options.keys()))
user_id = options[selected]

if st.button("生成画像报告", type="primary"):
    with st.spinner("正在生成综合画像..."):
        profile = generate_profile(user_id)

    if "error" in profile and "person" not in profile:
        st.error(profile["error"])
        st.stop()

    person = profile["person"]
    stats = profile.get("basic_stats", {})
    overall_risk = profile.get("overall_risk", "LOW")

    # ==================== 风险评级卡片 ====================
    risk_colors = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
    risk_labels = {"HIGH": "高风险", "MEDIUM": "中风险", "LOW": "低风险"}

    st.markdown(f"### {person.get('name', '未知')} 画像总览")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("综合风险评级", risk_labels[overall_risk])
    col2.metric("交易笔数", f"{stats.get('total_tx', 0):,}")
    col3.metric("总入账", f"{stats.get('total_income_yuan', 0):,.0f}元")
    col4.metric("总出账", f"{stats.get('total_expense_yuan', 0):,.0f}元")

    # ==================== 基本信息 ====================
    with st.expander("基本信息", expanded=True):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**姓名**: {person.get('name', '')}")
            st.markdown(f"**身份证号**: {person.get('id_card', '')}")
            st.markdown(f"**账号**: {person.get('user_id', '')}")
        with col_b:
            st.markdown(f"**手机**: {person.get('phone', '')}")
            st.markdown(f"**注册时间**: {person.get('reg_time', '')}")
            cards = profile.get("cards", [])
            st.markdown(f"**银行卡**: {len(cards)}张")
            for c in cards:
                st.caption(f"  {c.get('bank_name', '')} {c.get('card_no', '')} ({c.get('status', '')})")

    # ==================== 风险预警 ====================
    with st.expander("风险预警", expanded=True):
        risk_items = profile.get("risk_items", [])
        if risk_items:
            for item in risk_items:
                if item["risk_level"] == "HIGH":
                    st.error(f"**[{item['type']}]** {item['description']}")
                else:
                    st.warning(f"**[{item['type']}]** {item['description']}")
        else:
            st.success("未发现明显异常风险。")

    # ==================== 交易用途分布 ====================
    with st.expander("交易用途分布"):
        purpose_data = profile.get("purpose_distribution", [])
        if purpose_data:
            df_purpose = pd.DataFrame(purpose_data)
            fig = px.pie(df_purpose, names="purpose", values="count", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    # ==================== 交易时段 ====================
    with st.expander("交易时段分布"):
        hour_data = profile.get("hour_distribution", {})
        if hour_data:
            df_hour = pd.DataFrame(
                [{"hour": int(h), "count": c} for h, c in hour_data.items()]
            ).sort_values("hour")
            fig = px.bar(df_hour, x="hour", y="count",
                        labels={"hour": "小时", "count": "交易笔数"})
            fig.add_vrect(x0=-0.5, x1=5.5, fillcolor="red", opacity=0.1,
                         annotation_text="深夜时段")
            st.plotly_chart(fig, use_container_width=True)

    # ==================== 关键关系人 ====================
    with st.expander("关键关系人"):
        top_contacts = profile.get("top_contacts", [])
        if top_contacts:
            df_contacts = pd.DataFrame(top_contacts)
            df_contacts.columns = ["姓名", "出账(元)", "入账(元)", "交易笔数"]
            st.dataframe(df_contacts, use_container_width=True, hide_index=True)

    # ==================== 过桥账户 ====================
    bridges = profile.get("bridge_accounts", [])
    if bridges:
        with st.expander("疑似过桥账户"):
            for b in bridges[:5]:
                ds = b.get("downstream", b.get("upstream", []))
                st.markdown(
                    f"- **{b['bridge_name']}**: "
                    f"流入{b['flow_in']:,.0f}元 / 流出{b['flow_out']:,.0f}元, "
                    f"关联: {', '.join(str(d) for d in ds)}"
                )

    # ==================== 文本报告 ====================
    st.divider()
    st.subheader("完整文本报告")
    report_text = generate_report_text(profile)
    st.text(report_text)

    st.download_button(
        "下载报告",
        data=report_text.encode("utf-8"),
        file_name=f"画像报告_{person.get('name', user_id)}.txt",
        mime="text/plain",
    )
