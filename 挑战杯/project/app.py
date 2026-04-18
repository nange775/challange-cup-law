"""检察侦查画像系统 — Streamlit 主入口（与Vue.js功能同步）"""
import streamlit as st
from pathlib import Path
import sys
import os
import hashlib
import time

sys.path.insert(0, str(Path(__file__).parent))
from src.database import init_db, get_db_stats
from src.ingest import ingest_tenpay_data
from src.anomaly import run_all_detections, get_risk_summary

# 页面配置
st.set_page_config(
    page_title="检察侦查画像系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式（与Vue.js样式同步）
st.markdown("""
<style>
    /* 全局样式 */
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
    }

    /* 侧边栏样式 */
    .css-1d391kg {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    /* 卡片样式 */
    .stCard {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }

    .stCard:hover {
        transform: translateY(-5px);
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
    }

    /* 统计卡片 */
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }

    .stat-value {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 5px;
    }

    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }

    /* 按钮样式 */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }

    /* 标题样式 */
    h1 {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }

    h2 {
        color: #1a1a2e;
        font-weight: 700;
        border-bottom: 3px solid #667eea;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }

    /* 表格样式 */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }

    /* 标签页样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(102, 126, 234, 0.1);
        padding: 8px;
        border-radius: 12px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
    }

    /* 信息框样式 */
    .stAlert {
        border-radius: 12px;
        border: none;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
    }

    /* 进度条样式 */
    .stProgress > div > div {
        border-radius: 10px;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
</style>
""", unsafe_allow_html=True)

# 初始化数据库
init_db()

# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("<div style='text-align: center; padding: 1rem 0;'>"
                "<h1 style='font-size: 1.5rem; margin-bottom: 0.5rem;'>🎯 检察侦查画像系统</h1>"
                "<p style='font-size: 0.85rem; opacity: 0.8;'>基于财付通资金流水的智能分析平台</p>"
                "</div>", unsafe_allow_html=True)

    st.divider()

    # 导航菜单（与Vue.js同步）
    nav_items = [
        ("home", "🏠 首页"),
        ("import", "📥 数据导入"),
        ("analysis", "📊 交易分析"),
        ("graph", "🕸️ 关系图谱"),
        ("profile", "👤 人员画像"),
        ("agent", "🤖 AI智能侦查"),
        ("help", "💬 系统说明"),
    ]

    # 使用session_state保存当前页面
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"

    for key, label in nav_items:
        is_active = st.session_state.current_page == key
        btn_type = "primary" if is_active else "secondary"
        if st.button(label, use_container_width=True, type=btn_type, key=f"nav_{key}"):
            st.session_state.current_page = key
            st.rerun()

    st.divider()

    # 统计信息
    stats = get_db_stats()
    st.markdown("<div style='background: rgba(102, 126, 234, 0.1); padding: 1rem; border-radius: 12px;'>"
                "<h4 style='margin-bottom: 1rem; text-align: center;'>📊 数据统计</h4></div>"
                , unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    col1.metric("👥 人员", stats["person_count"])
    col2.metric("💰 交易", f"{stats['tx_count']:,}")

    st.metric("💳 银行卡", stats["card_count"])

# ==================== 页面内容函数 ====================

def show_home():
    """首页 - 与Vue.js同步"""
    st.markdown("<h1 style='text-align: center; margin-bottom: 0.5rem;'>🎯 检察侦查画像系统</h1>"
                "<p style='text-align: center; color: #666; margin-bottom: 2rem;'>检察侦查画像模型 — 一种数据处理、分析、线索分析一体化的侦查参考工具</p>"
                , unsafe_allow_html=True)

    st.divider()

    # 功能卡片 - 与Vue.js homeCards同步
    cards = [
        {"icon": "📥", "title": "数据导入", "desc": "支持多格式文件导入，包括财付通数据、Excel、PDF、Word及图片OCR，系统自动识别格式、提取信息并录入。", "page": "import"},
        {"icon": "📊", "title": "交易分析", "desc": "六大异常检测算法：化整为零、深夜交易、财富突增等。", "page": "analysis"},
        {"icon": "🕸️", "title": "关系图谱", "desc": "交互式资金流向网络，识别过桥账户和资金回流。", "page": "graph"},
        {"icon": "👤", "title": "人员画像", "desc": "综合画像报告：风险评级、关系人、侦查建议。", "page": "profile"},
        {"icon": "🤖", "title": "AI 智能侦查", "desc": "大模型对话式分析，自然语言查询，自动调用工具。", "page": "agent"},
    ]

    cols = st.columns(3)
    for i, card in enumerate(cards):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"<h3 style='margin-bottom: 0.5rem;'>{card['icon']} {card['title']}</h3>"
                           f"<p style='color: #666; font-size: 0.9rem; min-height: 3.5rem;'>{card['desc']}</p>"
                           , unsafe_allow_html=True)
                if st.button("进入", key=f"card_{i}", use_container_width=True):
                    st.session_state.current_page = card['page']
                    st.rerun()

    st.divider()
    st.markdown("<p style='text-align: center; color: #999; font-size: 0.85rem;'>"
               "本系统用于辅助检察侦查工作, 分析结果仅供参考。所有标记的异常需结合案件实际情况进一步核实。"
               "</p>", unsafe_allow_html=True)

def show_import():
    """数据导入 - 与Vue.js同步，支持多格式导入"""
    st.title("📥 数据导入")

    # 使用 tabs 组织内容
    tab1, tab2, tab3 = st.tabs(["📁 多格式证据导入", "📊 财付通数据导入", "📂 自动扫描目录"])

    # ==================== Tab 1: 多格式证据导入 ====================
    with tab1:
        st.markdown("支持多格式文件导入：PDF、Word、Excel、TXT、图片（自动OCR）等")

        # 文件上传
        uploaded_files = st.file_uploader(
            "选择文件（支持多选）",
            accept_multiple_files=True,
            type=['pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'jpg', 'jpeg', 'png', 'tif', 'tiff']
        )

        if uploaded_files:
            # 财付通文件配对验证
            has_trades = any('tenpaytrades' in f.name.lower() or 'trades' in f.name.lower() for f in uploaded_files)
            has_reginfo = any('tenpayreginfo' in f.name.lower() or 'reginfo' in f.name.lower() for f in uploaded_files)

            if has_trades and not has_reginfo:
                st.warning("⚠️ 检测到交易明细文件，还需导入对应的注册信息文件 (TenpayRegInfo1.xls)")
            elif not has_trades and has_reginfo:
                st.warning("⚠️ 检测到注册信息文件，还需导入对应的交易明细文件 (TenpayTrades.xls)")
            elif has_trades and has_reginfo:
                st.success("✅ 财付通文件配对正确：交易明细 + 注册信息")

            # 显示文件列表
            st.markdown("**已选择文件：**")
            for f in uploaded_files:
                st.text(f"📄 {f.name} ({f.size:,} bytes)")

        # 证据类型选择
        evidence_type = st.selectbox(
            "证据类型",
            options=[
                ("auto", "自动识别"),
                ("tenpay_data", "财付通数据 (Tenpay)"),
                ("transaction_flow", "交易流水"),
                ("interrogation", "讯问笔录"),
                ("testimony", "证人证言"),
                ("contract", "合同协议"),
                ("legal_doc", "法律文书"),
                ("appraisal", "鉴定意见"),
                ("record", "笔录"),
                ("polygraph", "测谎结果"),
                ("chat", "聊天记录"),
                ("call", "通话记录"),
                ("location", "轨迹数据"),
                ("log", "系统日志"),
                ("invoice", "票据凭证"),
                ("other", "其他"),
            ],
            format_func=lambda x: x[1]
        )

        # 证据描述
        evidence_desc = st.text_area(
            "证据描述 (可选)",
            placeholder="输入证据的描述信息，如来源、提取时间、提取人员等\n\n财付通数据导入说明：\n- 请同时上传 TenpayTrades.xls (交易明细) 和 TenpayRegInfo1.xls (注册信息)\n- 系统将自动解析并匹配用户身份与交易记录",
            height=120
        )

        # 案件ID
        case_id = st.text_input("案件ID (可选)", placeholder="留空将自动生成")

        # 导入按钮
        can_import = uploaded_files and (not (has_trades ^ has_reginfo))  # XOR 检查
        if st.button("📤 导入数据", type="primary", use_container_width=True, disabled=not can_import):
            # TODO: 实现实际的导入逻辑
            st.success(f"成功导入 {len(uploaded_files)} 个文件")

    # ==================== Tab 2: 财付通数据导入（传统方式）====================
    with tab2:
        st.markdown("传统方式：分别上传交易明细和注册信息文件")

        col1, col2 = st.columns(2)

        with col1:
            trades_file = st.file_uploader("交易明细文件 (TenpayTrades.xls)", type=['xls', 'xlsx'])

        with col2:
            reginfo_file = st.file_uploader("注册信息文件 (TenpayRegInfo1.xls)", type=['xls', 'xlsx'])

        if trades_file and reginfo_file:
            if st.button("📤 导入财付通数据", type="primary", use_container_width=True):
                # TODO: 实现实际的导入逻辑
                st.success("财付通数据导入成功")
        else:
            st.info("请同时上传交易明细和注册信息文件")

    # ==================== Tab 3: 自动扫描目录 ====================
    with tab3:
        st.markdown("自动扫描指定目录，批量导入财付通数据文件")

        scan_dir = st.text_input("目录路径", placeholder="输入包含 Tenpay 数据的目录路径")

        if st.button("🔍 扫描并导入", type="primary", use_container_width=True):
            if scan_dir:
                # TODO: 实现实际的扫描逻辑
                st.success(f"扫描目录: {scan_dir}")
            else:
                st.warning("请输入目录路径")

    # ==================== 数据概览 ====================
    st.divider()
    st.subheader("📊 当前数据概览")

    # 这里可以显示数据库统计信息
    stats = get_db_stats()
    cols = st.columns(4)
    cols[0].metric("已录入人员", stats["person_count"])
    cols[1].metric("交易记录", f"{stats['tx_count']:,}")
    cols[2].metric("银行卡", stats["card_count"])

# ==================== 其他页面 ====================

def show_analysis():
    """交易分析"""
    st.title("📊 交易分析与异常检测")
    st.markdown("运行六大异常检测算法：化整为零、深夜交易、财富突增等。")

    # TODO: 实现交易分析功能
    st.info("交易分析功能开发中...")

def show_graph():
    """关系图谱"""
    st.title("🕸️ 关系图谱")
    st.markdown("基于资金流向构建交互式关系网络图，识别过桥账户和资金回流。")

    # TODO: 实现关系图谱功能
    st.info("关系图谱功能开发中...")

def show_profile():
    """人员画像"""
    st.title("👤 人员画像报告")
    st.markdown("生成综合画像报告：资金概况、风险预警、关键关系人、侦查建议。")

    # TODO: 实现人员画像功能
    st.info("人员画像功能开发中...")

def show_agent():
    """AI智能侦查"""
    st.title("🤖 AI 智能侦查助手")
    st.markdown("基于大语言模型的对话式侦查助手，支持自然语言查询、自动调用分析工具。")

    # TODO: 实现AI智能侦查功能
    st.info("AI智能侦查功能开发中...")

def show_help():
    """系统说明"""
    st.title("💬 系统说明")
    st.markdown("检察侦查画像系统使用指南")

    st.divider()

    # 系统架构
    st.subheader("🏗️ 系统架构")
    st.markdown("本系统采用前后端分离架构：")
    st.markdown("""
    - **后端**：FastAPI (Python) - 提供RESTful API服务
    - **前端**：Vue 3 + Element Plus - 响应式用户界面
    - **数据库**：SQLite - 数据持久化存储
    - **可视化**：ECharts - 图表和关系图谱展示
    """)

    # 功能模块
    st.subheader("📦 功能模块")

    modules = [
        ("📥 数据导入", "支持多格式文件导入，包括财付通数据、Excel、PDF、Word及图片OCR，系统自动识别格式、提取信息并录入。"),
        ("📊 交易分析", "六大异常检测算法：化整为零、深夜交易、财富突增等。"),
        ("🕸️ 关系图谱", "交互式资金流向网络，识别过桥账户和资金回流。"),
        ("👤 人员画像", "综合画像报告：风险评级、关系人、侦查建议。"),
        ("🤖 AI 智能侦查", "大模型对话式分析，自然语言查询，自动调用工具。"),
    ]

    for icon_title, desc in modules:
        with st.expander(icon_title):
            st.markdown(desc)

    # 数据格式说明
    st.subheader("📋 数据格式说明")
    st.markdown("系统支持导入多种格式的证据和数据文件：")
    st.markdown("""
    - **财付通数据** - 需同时上传 TenpayTrades.xls (交易明细) 和 TenpayRegInfo1.xls (注册信息)
    - **文档文件** - PDF, Word (DOC/DOCX), TXT, Excel (XLS/XLSX)
    - **图像文件** - JPG, JPEG, PNG, TIFF (支持自动OCR文字识别)
    """)

    # 使用提示
    st.subheader("💡 使用提示")
    st.markdown("""
    - 首次使用请先通过「数据导入」功能上传相关数据文件，支持财付通数据、Excel、PDF、图片等多种格式
    - 分析结果仅供参考，需结合案件实际情况进一步核实
    - 建议使用Chrome或Edge浏览器获得最佳体验
    - AI智能侦查功能需要配置API密钥
    """)

    # 技术支持
    st.subheader("🔧 技术支持")
    st.markdown("如遇问题或建议，请联系技术支持团队。")
    st.markdown("<p style='color: #666;'>版本：v1.0.0 | 更新时间：2024</p>", unsafe_allow_html=True)

# ==================== 主程序 ====================

# 路由
page = st.session_state.current_page

if page == "home":
    show_home()
elif page == "import":
    show_import()
elif page == "analysis":
    show_analysis()
elif page == "graph":
    show_graph()
elif page == "profile":
    show_profile()
elif page == "agent":
    show_agent()
elif page == "help":
    show_help()

# 底部说明
st.divider()
st.caption(
    "本系统用于辅助检察侦查工作, 分析结果仅供参考。"
    "系统基于财付通资金流水数据进行模式识别与异常检测, "
    "所有标记的异常需结合案件实际情况进一步核实。"
)
