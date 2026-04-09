"""数据导入与清洗模块 — 解析 Tenpay XLS 文件并写入 SQLite"""
import pandas as pd
import sqlite3
import re
from pathlib import Path
from typing import Tuple
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import get_conn, init_db

# Tenpay 交易明细标准列名映射(按位置)
TRADE_COLS = [
    "user_id", "trade_no", "big_trade_no", "user_account_name",
    "direction", "biz_type", "purpose", "trade_time",
    "amount", "balance", "user_card", "user_net_union_no",
    "net_union", "third_party_account", "counterpart_id",
    "counterpart_account", "counterpart_card", "counterpart_bank",
    "counterpart_net_union_no", "net_union2", "fund_company",
    "inter_connected", "third_party_account2", "counterpart_recv_time",
    "counterpart_recv_amount", "remark1", "remark2"
]

# 注册信息标准列名映射(按位置)
REG_COLS = [
    "account_status", "user_id", "reg_name", "reg_time",
    "id_card", "phone", "bindcard_status", "bank_name", "card_no"
]


def _clean_counterpart_id(raw: str) -> str:
    """提取对手方ID中的纯ID部分"""
    if pd.isna(raw) or raw == "":
        return ""
    s = str(raw)
    # 格式: "名称(id)" -> 取id
    m = re.search(r'\(([^)]+)\)$', s)
    if m:
        return m.group(1)
    return s


def _clean_counterpart_name(raw_name, raw_id) -> str:
    """提取对手方名称"""
    if pd.notna(raw_name) and str(raw_name).strip():
        return str(raw_name).strip()
    if pd.isna(raw_id):
        return ""
    s = str(raw_id)
    m = re.match(r'^(.+?)\(', s)
    if m:
        return m.group(1)
    return ""


def parse_trades_xls(file_path: str) -> pd.DataFrame:
    """解析 TenpayTrades.xls 文件"""
    df = pd.read_excel(file_path)
    # 统一列名
    if len(df.columns) == len(TRADE_COLS):
        df.columns = TRADE_COLS
    else:
        raise ValueError(f"交易文件列数不匹配: 期望{len(TRADE_COLS)}, 实际{len(df.columns)}")

    # 清洗
    # XLS合并单元格导致user_id只有首行有值, 需前向填充
    df["user_id"] = df["user_id"].ffill()
    df["user_account_name"] = df["user_account_name"].ffill()
    df = df.dropna(subset=["user_id"])
    df["trade_time"] = pd.to_datetime(df["trade_time"], errors="coerce")
    df = df.dropna(subset=["trade_time"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype(int).abs()
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(0).astype(int)
    df["direction"] = df["direction"].astype(str).str.strip()

    # 清洗对手方信息
    df["counterpart_name_clean"] = df.apply(
        lambda r: _clean_counterpart_name(r["counterpart_account"], r["counterpart_id"]),
        axis=1
    )
    df["counterpart_id_clean"] = df["counterpart_id"].apply(_clean_counterpart_id)

    return df


def parse_reginfo_xls(file_path: str) -> Tuple[dict, list]:
    """解析 TenpayRegInfo1.xls 文件, 返回 (人员信息dict, 银行卡列表)"""
    df = pd.read_excel(file_path)
    if len(df.columns) == len(REG_COLS):
        df.columns = REG_COLS

    # 第一行是正常注册信息
    person = {
        "user_id": str(df.iloc[0]["user_id"]).strip(),
        "name": str(df.iloc[0].get("reg_name", "")).strip(),
        "id_card": str(df.iloc[0].get("id_card", "")).strip(),
        "phone": str(df.iloc[0].get("phone", "")).strip(),
        "reg_time": str(df.iloc[0].get("reg_time", "")),
    }

    # 提取所有银行卡信息(第一行及后续行)
    cards = []
    for _, row in df.iterrows():
        card_no = row.get("card_no")
        bank_name = row.get("bank_name")
        status = row.get("bindcard_status")
        if (pd.notna(card_no) and str(card_no).strip()
                and str(card_no) != "银行账号"
                and not str(card_no).startswith("解绑")):
            cards.append({
                "user_id": person["user_id"],
                "card_no": str(card_no).strip(),
                "bank_name": str(bank_name).strip() if pd.notna(bank_name) else "",
                "status": str(status).strip() if pd.notna(status) else "",
            })

    return person, cards


def ingest_tenpay_data(trades_path: str, reginfo_path: str) -> dict:
    """
    导入一组 Tenpay 数据(一个用户的交易明细+注册信息)到数据库。
    返回导入统计。
    """
    init_db()

    # 先解析文件(在获取连接前, 避免长时间锁库)
    person, cards = parse_reginfo_xls(reginfo_path)
    user_id = person["user_id"]
    trades_df = parse_trades_xls(trades_path)

    conn = get_conn()
    try:
        # 写入人员表(upsert)
        conn.execute("""
            INSERT OR REPLACE INTO persons (user_id, name, id_card, phone, reg_time)
            VALUES (?, ?, ?, ?, ?)
        """, (person["user_id"], person["name"], person["id_card"],
              person["phone"], person["reg_time"]))

        # 写入银行卡
        conn.execute("DELETE FROM bank_cards WHERE user_id = ?", (user_id,))
        for card in cards:
            conn.execute("""
                INSERT INTO bank_cards (user_id, card_no, bank_name, status)
                VALUES (?, ?, ?, ?)
            """, (card["user_id"], card["card_no"], card["bank_name"], card["status"]))

        # 删除该用户旧数据后重新写入
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        rows_inserted = 0
        for _, row in trades_df.iterrows():
            conn.execute("""
                INSERT INTO transactions
                    (trade_no, big_trade_no, user_id, user_name, direction,
                     biz_type, purpose, trade_time, amount, balance,
                     user_card, counterpart_id, counterpart_name,
                     counterpart_card, counterpart_bank, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row["trade_no"]),
                str(row["big_trade_no"]),
                str(row["user_id"]),
                str(row["user_account_name"]),
                str(row["direction"]),
                str(row["biz_type"]),
                str(row["purpose"]),
                str(row["trade_time"]),
                int(row["amount"]),
                int(row["balance"]),
                str(row["user_card"]) if pd.notna(row["user_card"]) else None,
                row["counterpart_id_clean"],
                row["counterpart_name_clean"],
                str(row["counterpart_card"]) if pd.notna(row["counterpart_card"]) else None,
                str(row["counterpart_bank"]) if pd.notna(row["counterpart_bank"]) else None,
                str(row.get("remark1", "")) if pd.notna(row.get("remark1")) else None,
            ))
            rows_inserted += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "user_id": user_id,
        "name": person["name"],
        "cards_count": len(cards),
        "tx_count": rows_inserted,
    }


def auto_discover_and_ingest(root_dir: str) -> list:
    """
    自动扫描目录结构, 发现并导入所有 Tenpay 数据。
    支持目录结构: .../IDCARD/身份证号/用户ID/TenpayTrades.xls
    """
    root = Path(root_dir)
    results = []

    # 查找所有 TenpayTrades.xls
    for trades_file in root.rglob("TenpayTrades.xls"):
        user_dir = trades_file.parent
        # 查找对应的注册信息文件
        # 注册信息可能在同级目录或平行目录
        reg_file = None
        # 先在同目录找
        for candidate in user_dir.glob("TenpayRegInfo*.xls"):
            reg_file = candidate
            break
        # 在平行目录结构中找
        if reg_file is None:
            id_card_dir = user_dir.parent  # IDCARD/身份证号
            user_id_name = user_dir.name
            # 从 交易明细 跳到 注册信息
            for alt_root in root.rglob("注册信息"):
                for candidate in alt_root.rglob(f"{user_id_name}/TenpayRegInfo*.xls"):
                    reg_file = candidate
                    break
                if reg_file:
                    break

        if reg_file is None:
            results.append({"error": f"未找到 {trades_file} 对应的注册信息文件"})
            continue

        try:
            stats = ingest_tenpay_data(str(trades_file), str(reg_file))
            results.append(stats)
        except Exception as e:
            results.append({"error": f"导入失败 {trades_file}: {e}"})

    return results
