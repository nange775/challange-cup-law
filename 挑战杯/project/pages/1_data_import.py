"""数据导入页面"""
import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import init_db, get_db_stats, clear_db, get_all_persons
from src.ingest import ingest_tenpay_data, auto_discover_and_ingest

init_db()

st.title("数据导入")

tab1, tab2 = st.tabs(["手动上传", "自动扫描目录"])

# ==================== 手动上传 ====================
with tab1:
    st.subheader("上传 Tenpay 数据文件")
    st.markdown("请分别上传同一用户的**交易明细**(TenpayTrades.xls)和**注册信息**(TenpayRegInfo1.xls)。")

    col1, col2 = st.columns(2)
    with col1:
        trades_file = st.file_uploader("交易明细 (TenpayTrades.xls)", type=["xls", "xlsx"], key="trades")
    with col2:
        reg_file = st.file_uploader("注册信息 (TenpayRegInfo1.xls)", type=["xls", "xlsx"], key="reg")

    if st.button("导入数据", disabled=not (trades_file and reg_file)):
        with st.spinner("正在导入数据..."):
            # 保存上传文件到临时目录
            with tempfile.TemporaryDirectory() as tmpdir:
                trades_path = Path(tmpdir) / "TenpayTrades.xls"
                reg_path = Path(tmpdir) / "TenpayRegInfo1.xls"
                trades_path.write_bytes(trades_file.read())
                reg_path.write_bytes(reg_file.read())

                try:
                    result = ingest_tenpay_data(str(trades_path), str(reg_path))
                    st.success(
                        f"导入成功! 用户: {result['name']}({result['user_id']}), "
                        f"银行卡: {result['cards_count']}张, "
                        f"交易记录: {result['tx_count']}笔"
                    )
                except Exception as e:
                    st.error(f"导入失败: {e}")

# ==================== 自动扫描 ====================
with tab2:
    st.subheader("自动扫描数据目录")
    st.markdown("输入包含 Tenpay 数据的根目录路径, 系统会自动发现并导入所有用户数据。")

    default_dir = str(Path(__file__).parent.parent.parent / "数据包")
    data_dir = st.text_input("数据目录路径", value=default_dir)

    if st.button("开始扫描并导入"):
        if not Path(data_dir).exists():
            st.error(f"目录不存在: {data_dir}")
        else:
            with st.spinner("扫描并导入中..."):
                results = auto_discover_and_ingest(data_dir)
                if not results:
                    st.warning("未发现可导入的数据文件。")
                else:
                    for r in results:
                        if "error" in r:
                            st.error(r["error"])
                        else:
                            st.success(
                                f"导入: {r['name']}({r['user_id']}), "
                                f"银行卡{r['cards_count']}张, 交易{r['tx_count']}笔"
                            )

# ==================== 数据概览 ====================
st.divider()
st.subheader("当前数据概览")

stats = get_db_stats()
col1, col2, col3 = st.columns(3)
col1.metric("已录入人员", stats["person_count"])
col2.metric("交易记录", f"{stats['tx_count']:,}")
col3.metric("银行卡", stats["card_count"])

persons = get_all_persons()
if not persons.empty:
    persons.columns = ["用户ID", "姓名", "身份证号", "手机号", "注册时间"]
    st.dataframe(persons, use_container_width=True, hide_index=True)

# 清空数据
st.divider()
with st.expander("危险操作"):
    if st.button("清空所有数据", type="secondary"):
        clear_db()
        st.warning("所有数据已清空。")
        st.rerun()
