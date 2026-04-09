"""AI 智能侦查对话页面 — 支持多厂商 LLM"""
import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import init_db, get_db_stats
from src.agent import chat_with_agent
from config import LLM_PROVIDERS, get_provider_api_key

init_db()

st.title("AI 智能侦查助手")
st.caption("基于大语言模型的对话式侦查分析, 支持多厂商模型, 自动调用数据分析工具。")

# ==================== 侧边栏: 模型配置 ====================
with st.sidebar:
    st.subheader("模型配置")

    # 厂商选择
    provider_options = {pid: p["name"] for pid, p in LLM_PROVIDERS.items()}
    provider_id = st.selectbox(
        "选择厂商",
        list(provider_options.keys()),
        format_func=lambda x: provider_options[x],
        key="provider",
    )

    provider = LLM_PROVIDERS[provider_id]

    # 模型选择
    if provider_id == "custom":
        model = st.text_input("模型名称", placeholder="e.g. my-model-v1")
        custom_base_url = st.text_input("Base URL", placeholder="https://your-api.com/v1")
    else:
        model_options = provider["models"]
        model = st.selectbox(
            "模型",
            model_options,
            index=model_options.index(provider["default_model"]) if provider["default_model"] in model_options else 0,
        )
        custom_base_url = None

    # API Key
    env_key_hint = f"(环境变量: {provider['env_key']})" if provider.get("env_key") else ""
    default_key = get_provider_api_key(provider_id)
    api_key = st.text_input(
        f"API Key {env_key_hint}",
        value=default_key,
        type="password",
        key="api_key",
    )

    # 状态信息
    st.divider()
    stats = get_db_stats()
    st.caption(f"数据库: {stats['person_count']}人, {stats['tx_count']:,}笔交易")
    st.caption(f"协议: {provider['protocol']} | 模型: {model}")

    st.divider()
    st.markdown("**示例问题:**")
    st.caption("- 帮我分析jerry123的资金异常情况")
    st.caption("- 李四与宗正貌之间有哪些交易?")
    st.caption("- 生成李四的完整画像报告")
    st.caption("- 李四在2023年3-5月有什么异常?")
    st.caption("- 哪些月份李四的入账金额异常高?")

# ==================== 对话区域 ====================

# 初始化对话历史
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []
if "agent_chat_history" not in st.session_state:
    st.session_state.agent_chat_history = []

# 显示历史消息
for msg in st.session_state.agent_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 用户输入
if prompt := st.chat_input("请输入您的侦查分析需求..."):
    st.session_state.agent_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"正在调用 {provider['name']} ({model}) 分析中..."):
            api_messages = st.session_state.agent_chat_history + [
                {"role": "user", "content": prompt}
            ]

            reply, updated_history = chat_with_agent(
                messages=api_messages,
                provider_id=provider_id,
                api_key=api_key or None,
                model=model or None,
                base_url=custom_base_url,
            )
            st.session_state.agent_chat_history = updated_history
            st.markdown(reply)

    st.session_state.agent_messages.append({"role": "assistant", "content": reply})

# 清空对话
if st.button("清空对话"):
    st.session_state.agent_messages = []
    st.session_state.agent_chat_history = []
    st.rerun()
