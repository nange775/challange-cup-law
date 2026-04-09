"""关系图谱页面"""
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import init_db, get_all_persons, get_person_transactions
from src.graph_analysis import (
    build_transaction_graph, find_bridge_accounts, find_fund_cycles,
    get_network_metrics, get_top_counterparts, generate_pyvis_html,
)

init_db()

st.title("关系图谱分析")

persons = get_all_persons()
if persons.empty:
    st.warning("请先在「数据导入」页面导入数据。")
    st.stop()

options = {f"{row['name']}({row['user_id']})": row for _, row in persons.iterrows()}
selected = st.selectbox("选择分析对象", list(options.keys()))
person = options[selected]
user_id = person["user_id"]
target_name = person["name"]

tx = get_person_transactions(user_id)
if tx.empty:
    st.warning("该用户无交易数据。")
    st.stop()

# 构建图谱
G = build_transaction_graph(tx)

# ==================== 网络指标 ====================
st.subheader("网络指标")
metrics = get_network_metrics(G, target_name)
if metrics:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总度数", metrics.get("degree", 0))
    col2.metric("入度(收款来源)", metrics.get("in_degree", 0))
    col3.metric("出度(付款去向)", metrics.get("out_degree", 0))
    col4.metric("自然人联系人", metrics.get("person_contacts", 0))

# ==================== 交互式图谱 ====================
st.subheader("资金流向图谱")
st.caption("红色节点=分析目标, 蓝色=自然人, 灰色=企业/机构。边粗细反映金额大小, 红色边=大额流转。悬停可查看详情。")

try:
    html = generate_pyvis_html(G, target_name)
    components.html(html, height=650, scrolling=True)
except Exception as e:
    st.error(f"图谱生成失败: {e}")

# ==================== 过桥账户 ====================
st.subheader("疑似过桥账户(白手套)")
st.caption("在目标人物的交易网络中, 既接收目标资金又向外转出的中间人, 可能充当资金中转角色。")

bridges = find_bridge_accounts(G, target_name)
if bridges:
    for i, b in enumerate(bridges[:10], 1):
        downstream = b.get("downstream", b.get("upstream", []))
        direction_label = "出账方向" if b["direction"] == "出" else "入账方向"
        suspicion_pct = f"{b['suspicion']*100:.0f}%"

        with st.expander(f"{i}. {b['bridge_name']} ({direction_label}, 匹配度{suspicion_pct})"):
            col1, col2 = st.columns(2)
            col1.metric("流入金额", f"{b['flow_in']:,.0f} 元")
            col2.metric("流出金额", f"{b['flow_out']:,.0f} 元")
            st.markdown(f"**关联方**: {', '.join(str(d) for d in downstream)}")
else:
    st.info("未发现明显的过桥账户。")

# ==================== 资金回流 ====================
st.subheader("资金回流环路")
st.caption("A->B->C->A 形式的资金环路, 可能表明洗钱或掩饰资金来源。")

cycles = find_fund_cycles(G, target_name)
if cycles:
    for i, c in enumerate(cycles[:10], 1):
        path_str = " -> ".join(c["path"]) + " -> " + c["path"][0]
        st.markdown(f"**环路{i}**: {path_str} (瓶颈流量: {c['min_flow_yuan']:,.0f}元)")
else:
    st.info("未发现资金回流环路。")

# ==================== 关键关系人 ====================
st.subheader("关键关系人排名")
top = get_top_counterparts(G, target_name, top_n=15)
if top:
    import pandas as pd
    df_top = pd.DataFrame(top)
    df_top.columns = ["姓名/名称", "出账(元)", "入账(元)", "交易笔数"]
    df_top["出账(元)"] = df_top["出账(元)"].apply(lambda x: f"{x:,.0f}")
    df_top["入账(元)"] = df_top["入账(元)"].apply(lambda x: f"{x:,.0f}")
    st.dataframe(df_top, use_container_width=True, hide_index=True)
