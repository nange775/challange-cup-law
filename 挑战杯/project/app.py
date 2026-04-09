"""检察侦查画像系统 — Streamlit 主入口"""
import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from src.database import init_db, get_db_stats

st.set_page_config(
    page_title="检察侦查画像系统",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化数据库
init_db()

# 侧边栏
with st.sidebar:
    st.title("检察侦查画像系统")
    st.caption("基于财付通资金流水的智能分析平台")
    st.divider()

    stats = get_db_stats()
    st.metric("已录入人员", stats["person_count"])
    st.metric("交易记录数", f"{stats['tx_count']:,}")
    st.metric("关联银行卡", stats["card_count"])

# 主页内容
st.title("检察侦查画像系统")
st.markdown("**检察侦查画像模型 — 一种数据处理、分析、线索分析一体化的侦查参考工具**")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("数据导入")
    st.markdown(
        "上传财付通(Tenpay)交易明细与注册信息文件, "
        "系统自动清洗、融合并存入数据库。"
    )
    if st.button("前往数据导入", use_container_width=True):
        st.switch_page("pages/1_data_import.py")

with col2:
    st.subheader("异常检测与分析")
    st.markdown(
        "运行六大异常检测算法: 化整为零、深夜交易、"
        "财富突增、高频对手方、大额转账、整数金额模式。"
    )
    if st.button("前往交易分析", use_container_width=True):
        st.switch_page("pages/2_analysis.py")

with col3:
    st.subheader("关系图谱")
    st.markdown(
        "基于资金流向构建交互式关系网络图, "
        "识别过桥账户(白手套)和资金回流环路。"
    )
    if st.button("前往关系图谱", use_container_width=True):
        st.switch_page("pages/3_graph.py")

st.divider()

col4, col5 = st.columns(2)

with col4:
    st.subheader("人员画像报告")
    st.markdown(
        "生成综合画像报告: 资金概况、风险预警、"
        "关键关系人、侦查建议, 输出规范的法言法语报告。"
    )
    if st.button("前往人员画像", use_container_width=True):
        st.switch_page("pages/4_profile.py")

with col5:
    st.subheader("AI 智能侦查")
    st.markdown(
        "基于大语言模型的对话式侦查助手, "
        "支持自然语言查询、自动调用分析工具。"
    )
    if st.button("前往智能侦查", use_container_width=True):
        st.switch_page("pages/5_agent.py")

# 底部说明
st.divider()
st.caption(
    "本系统用于辅助检察侦查工作, 分析结果仅供参考。"
    "系统基于财付通资金流水数据进行模式识别与异常检测, "
    "所有标记的异常需结合案件实际情况进一步核实。"
)
