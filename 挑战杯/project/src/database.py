"""SQLite 数据库操作模块"""
import sqlite3
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, DATA_DIR


def get_conn() -> sqlite3.Connection:
    """获取数据库连接"""
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS persons (
            user_id   TEXT PRIMARY KEY,
            name      TEXT,
            id_card   TEXT,
            phone     TEXT,
            reg_time  TEXT
        );

        CREATE TABLE IF NOT EXISTS bank_cards (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            card_no   TEXT,
            bank_name TEXT,
            status    TEXT,
            FOREIGN KEY (user_id) REFERENCES persons(user_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_no          TEXT,
            big_trade_no      TEXT,
            user_id           TEXT NOT NULL,
            user_name         TEXT,
            direction         TEXT,       -- 入/出
            biz_type          TEXT,       -- 交易业务类型
            purpose           TEXT,       -- 交易用途类型
            trade_time        TEXT,
            amount            INTEGER,    -- 交易金额(分)
            balance           INTEGER,    -- 账户余额(分)
            user_card         TEXT,
            counterpart_id    TEXT,
            counterpart_name  TEXT,
            counterpart_card  TEXT,
            counterpart_bank  TEXT,
            remark            TEXT,
            FOREIGN KEY (user_id) REFERENCES persons(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(trade_time);
        CREATE INDEX IF NOT EXISTS idx_tx_counterpart ON transactions(counterpart_id);
        CREATE INDEX IF NOT EXISTS idx_tx_direction ON transactions(direction);
    """)
    conn.commit()
    conn.close()


def clear_db():
    """清空所有数据"""
    conn = get_conn()
    conn.executescript("""
        DELETE FROM transactions;
        DELETE FROM bank_cards;
        DELETE FROM persons;
    """)
    conn.commit()
    conn.close()


def get_all_persons() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM persons", conn)
    conn.close()
    return df


def get_all_transactions() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM transactions ORDER BY trade_time", conn)
    conn.close()
    if not df.empty:
        df["trade_time"] = pd.to_datetime(df["trade_time"])
        df["amount_yuan"] = df["amount"] / 100
    return df


def get_person_transactions(user_id: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY trade_time",
        conn, params=[user_id]
    )
    conn.close()
    if not df.empty:
        df["trade_time"] = pd.to_datetime(df["trade_time"])
        df["amount_yuan"] = df["amount"] / 100
    return df


def get_bank_cards(user_id: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql(
        "SELECT * FROM bank_cards WHERE user_id = ?",
        conn, params=[user_id]
    )
    conn.close()
    return df


def get_counterpart_summary(user_id: str) -> pd.DataFrame:
    """获取某用户的对手方汇总"""
    conn = get_conn()
    df = pd.read_sql("""
        SELECT
            counterpart_name,
            counterpart_id,
            COUNT(*) as tx_count,
            SUM(CASE WHEN direction='出' THEN amount ELSE 0 END) as total_out,
            SUM(CASE WHEN direction='入' THEN amount ELSE 0 END) as total_in,
            MIN(trade_time) as first_time,
            MAX(trade_time) as last_time
        FROM transactions
        WHERE user_id = ? AND counterpart_name IS NOT NULL AND counterpart_name != ''
        GROUP BY counterpart_name
        ORDER BY tx_count DESC
    """, conn, params=[user_id])
    conn.close()
    if not df.empty:
        df["total_out_yuan"] = df["total_out"] / 100
        df["total_in_yuan"] = df["total_in"] / 100
    return df


def get_db_stats() -> dict:
    """获取数据库统计信息"""
    conn = get_conn()
    stats = {
        "person_count": conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0],
        "card_count": conn.execute("SELECT COUNT(*) FROM bank_cards").fetchone()[0],
        "tx_count": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
    }
    conn.close()
    return stats
