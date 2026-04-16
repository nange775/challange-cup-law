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
        -- 案件表
        CREATE TABLE IF NOT EXISTS cases (
            case_id   TEXT PRIMARY KEY,
            case_name TEXT NOT NULL,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status    TEXT DEFAULT 'active'
        );

        -- 人员表（扩展）
        CREATE TABLE IF NOT EXISTS persons (
            user_id   TEXT PRIMARY KEY,
            case_id   TEXT,
            name      TEXT,
            id_card   TEXT,
            phone     TEXT,
            reg_time  TEXT,
            role      TEXT,  -- 嫌疑人/证人/涉案人
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS bank_cards (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            card_no   TEXT,
            bank_name TEXT,
            status    TEXT,
            FOREIGN KEY (user_id) REFERENCES persons(user_id)
        );

        -- 交易表（扩展）
        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id           TEXT,
            evidence_id       TEXT,
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
            source_type       TEXT DEFAULT '财付通',  -- 财付通/银行/支付宝
            FOREIGN KEY (user_id) REFERENCES persons(user_id),
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id)
        );

        -- 证据元数据表
        CREATE TABLE IF NOT EXISTS evidence_meta (
            evidence_id   TEXT PRIMARY KEY,
            case_id       TEXT NOT NULL,
            evidence_type TEXT NOT NULL,  -- 供述/证言/流水/聊天/文书/鉴定/笔录/测谎/其他
            title         TEXT,
            file_path     TEXT,
            event_time    TEXT,    -- 事件发生时间
            extract_time  TEXT,    -- 证据提取时间
            upload_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ai_summary    TEXT,    -- AI生成摘要
            status        TEXT DEFAULT '已分类',  -- 已分类/待审核
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        -- 人-证据关联表
        CREATE TABLE IF NOT EXISTS person_evidence_relation (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id   TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            role        TEXT,  -- 当事人/涉及人/证人
            FOREIGN KEY (person_id) REFERENCES persons(user_id),
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            UNIQUE(person_id, evidence_id)
        );

        -- 供述/辩解/证人证言
        CREATE TABLE IF NOT EXISTS statements (
            statement_id  TEXT PRIMARY KEY,
            evidence_id   TEXT NOT NULL,
            person_id     TEXT,
            statement_type TEXT,  -- 供述/辩解/证言
            content       TEXT,
            key_persons   TEXT,   -- JSON: 提到的人名
            key_amounts   TEXT,   -- JSON: 提到的金额
            key_events    TEXT,   -- JSON: 关键事件
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            FOREIGN KEY (person_id) REFERENCES persons(user_id)
        );

        -- 聊天记录
        CREATE TABLE IF NOT EXISTS chat_records (
            message_id   TEXT PRIMARY KEY,
            evidence_id  TEXT NOT NULL,
            sender_id    TEXT,
            receiver_id  TEXT,
            send_time    TEXT,
            content      TEXT,
            message_type TEXT DEFAULT '文本',  -- 文本/图片/转账
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            FOREIGN KEY (sender_id) REFERENCES persons(user_id),
            FOREIGN KEY (receiver_id) REFERENCES persons(user_id)
        );

        -- 文书类（判决/鉴定/笔录）
        CREATE TABLE IF NOT EXISTS documents (
            doc_id       TEXT PRIMARY KEY,
            evidence_id  TEXT NOT NULL,
            doc_subtype  TEXT,  -- 司法文书/鉴定意见/辨认笔录/测谎结果
            content      TEXT,
            key_info     TEXT,  -- JSON: AI提取的结论性意见
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id)
        );

        -- 轨迹数据
        CREATE TABLE IF NOT EXISTS location_records (
            record_id    TEXT PRIMARY KEY,
            evidence_id  TEXT NOT NULL,
            person_id    TEXT NOT NULL,
            record_time  TEXT,
            latitude     REAL,
            longitude    REAL,
            location_name TEXT,
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            FOREIGN KEY (person_id) REFERENCES persons(user_id)
        );

        -- 通话记录
        CREATE TABLE IF NOT EXISTS call_records (
            record_id   TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            caller_id   TEXT,
            callee_id   TEXT,
            call_time   TEXT,
            duration    INTEGER,  -- 秒
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            FOREIGN KEY (caller_id) REFERENCES persons(user_id),
            FOREIGN KEY (callee_id) REFERENCES persons(user_id)
        );

        -- 系统日志
        CREATE TABLE IF NOT EXISTS system_logs (
            log_id      TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            person_id   TEXT,
            log_time    TEXT,
            action      TEXT,  -- 登录/修改/删除
            ip_address  TEXT,
            details     TEXT,
            FOREIGN KEY (evidence_id) REFERENCES evidence_meta(evidence_id),
            FOREIGN KEY (person_id) REFERENCES persons(user_id)
        );

        -- 索引优化
        CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(trade_time);
        CREATE INDEX IF NOT EXISTS idx_tx_counterpart ON transactions(counterpart_id);
        CREATE INDEX IF NOT EXISTS idx_tx_direction ON transactions(direction);
        CREATE INDEX IF NOT EXISTS idx_tx_case ON transactions(case_id);
        CREATE INDEX IF NOT EXISTS idx_tx_evidence ON transactions(evidence_id);

        CREATE INDEX IF NOT EXISTS idx_persons_case ON persons(case_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence_meta(case_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence_meta(evidence_type);
        CREATE INDEX IF NOT EXISTS idx_per_rel_person ON person_evidence_relation(person_id);
        CREATE INDEX IF NOT EXISTS idx_per_rel_evidence ON person_evidence_relation(evidence_id);
        CREATE INDEX IF NOT EXISTS idx_chat_evidence ON chat_records(evidence_id);
        CREATE INDEX IF NOT EXISTS idx_chat_sender ON chat_records(sender_id);
        CREATE INDEX IF NOT EXISTS idx_location_person ON location_records(person_id);
        CREATE INDEX IF NOT EXISTS idx_call_caller ON call_records(caller_id);
        CREATE INDEX IF NOT EXISTS idx_call_callee ON call_records(callee_id);
    """)
    conn.commit()
    conn.close()


def clear_db():
    """清空所有数据"""
    conn = get_conn()
    conn.executescript("""
        DELETE FROM system_logs;
        DELETE FROM call_records;
        DELETE FROM location_records;
        DELETE FROM documents;
        DELETE FROM chat_records;
        DELETE FROM statements;
        DELETE FROM person_evidence_relation;
        DELETE FROM evidence_meta;
        DELETE FROM transactions;
        DELETE FROM bank_cards;
        DELETE FROM persons;
        DELETE FROM cases;
    """)
    conn.commit()
    conn.close()


def get_all_persons() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM persons", conn)
    conn.close()
    return df


def get_persons_with_transactions(exclude_companies: bool = False) -> pd.DataFrame:
    """
    获取有交易记录的人员列表
    exclude_companies: 是否排除企业（默认false，显示所有）
    """
    conn = get_conn()

    where_clause = ""
    if exclude_companies:
        # 排除名字中包含公司关键词的
        where_clause = """
        AND p.name NOT LIKE '%公司%'
        AND p.name NOT LIKE '%有限%'
        AND p.name NOT LIKE '%画廊%'
        AND p.name NOT LIKE '%商贸%'
        AND p.name NOT LIKE '%集团%'
        """

    df = pd.read_sql(f"""
        SELECT DISTINCT p.*, COUNT(t.id) as tx_count
        FROM persons p
        INNER JOIN transactions t ON p.user_id = t.user_id
        WHERE 1=1 {where_clause}
        GROUP BY p.user_id
        HAVING tx_count > 0
        ORDER BY tx_count DESC
    """, conn)
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
        "case_count": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        "evidence_count": conn.execute("SELECT COUNT(*) FROM evidence_meta").fetchone()[0],
    }
    conn.close()
    return stats


# ==================== 案件管理 ====================

def create_case(case_id: str, case_name: str) -> dict:
    """创建新案件"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO cases (case_id, case_name) VALUES (?, ?)",
            [case_id, case_name]
        )
        conn.commit()
        return {"success": True, "case_id": case_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "案件ID已存在"}
    finally:
        conn.close()


def get_all_cases() -> pd.DataFrame:
    """获取所有案件"""
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM cases ORDER BY create_time DESC", conn)
    conn.close()
    return df


def get_case_info(case_id: str) -> dict:
    """获取案件详情"""
    conn = get_conn()
    case = conn.execute(
        "SELECT * FROM cases WHERE case_id = ?", [case_id]
    ).fetchone()
    conn.close()
    if case:
        return {
            "case_id": case[0],
            "case_name": case[1],
            "create_time": case[2],
            "status": case[3]
        }
    return None


# ==================== 证据管理 ====================

def create_evidence(evidence_data: dict) -> str:
    """创建证据记录"""
    conn = get_conn()
    evidence_id = evidence_data.get('evidence_id')
    conn.execute("""
        INSERT INTO evidence_meta
        (evidence_id, case_id, evidence_type, title, file_path, event_time, extract_time, ai_summary, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        evidence_id,
        evidence_data.get('case_id'),
        evidence_data.get('evidence_type'),
        evidence_data.get('title'),
        evidence_data.get('file_path'),
        evidence_data.get('event_time'),
        evidence_data.get('extract_time'),
        evidence_data.get('ai_summary'),
        evidence_data.get('status', '已分类')
    ])
    conn.commit()
    conn.close()
    return evidence_id


def get_case_evidences(case_id: str) -> pd.DataFrame:
    """获取案件的所有证据"""
    conn = get_conn()
    df = pd.read_sql(
        "SELECT * FROM evidence_meta WHERE case_id = ? ORDER BY upload_time DESC",
        conn, params=[case_id]
    )
    conn.close()
    return df


def get_person_evidences(person_id: str) -> pd.DataFrame:
    """获取某人相关的所有证据"""
    conn = get_conn()
    df = pd.read_sql("""
        SELECT e.* FROM evidence_meta e
        JOIN person_evidence_relation r ON e.evidence_id = r.evidence_id
        WHERE r.person_id = ?
        ORDER BY e.upload_time DESC
    """, conn, params=[person_id])
    conn.close()
    return df


def link_person_evidence(person_id: str, evidence_id: str, role: str = '当事人'):
    """关联人员和证据"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO person_evidence_relation (person_id, evidence_id, role) VALUES (?, ?, ?)",
            [person_id, evidence_id, role]
        )
        conn.commit()
    finally:
        conn.close()


# ==================== 具体证据表操作 ====================

def insert_statement(statement_data: dict):
    """插入供述/证言"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO statements
        (statement_id, evidence_id, person_id, statement_type, content, key_persons, key_amounts, key_events)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        statement_data['statement_id'],
        statement_data['evidence_id'],
        statement_data['person_id'],
        statement_data.get('statement_type'),
        statement_data.get('content'),
        statement_data.get('key_persons'),
        statement_data.get('key_amounts'),
        statement_data.get('key_events')
    ])
    conn.commit()
    conn.close()


def insert_chat_records(chat_data: list):
    """批量插入聊天记录"""
    conn = get_conn()
    conn.executemany("""
        INSERT INTO chat_records
        (message_id, evidence_id, sender_id, receiver_id, send_time, content, message_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(
        r['message_id'],
        r['evidence_id'],
        r.get('sender_id'),
        r.get('receiver_id'),
        r.get('send_time'),
        r.get('content'),
        r.get('message_type', '文本')
    ) for r in chat_data])
    conn.commit()
    conn.close()


def insert_document(doc_data: dict):
    """插入文书"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO documents
        (doc_id, evidence_id, doc_subtype, content, key_info)
        VALUES (?, ?, ?, ?, ?)
    """, [
        doc_data['doc_id'],
        doc_data['evidence_id'],
        doc_data.get('doc_subtype'),
        doc_data.get('content'),
        doc_data.get('key_info')
    ])
    conn.commit()
    conn.close()


def insert_location_records(location_data: list):
    """批量插入轨迹数据"""
    conn = get_conn()
    conn.executemany("""
        INSERT INTO location_records
        (record_id, evidence_id, person_id, record_time, latitude, longitude, location_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(
        r['record_id'],
        r['evidence_id'],
        r['person_id'],
        r.get('record_time'),
        r.get('latitude'),
        r.get('longitude'),
        r.get('location_name')
    ) for r in location_data])
    conn.commit()
    conn.close()


def insert_call_records(call_data: list):
    """批量插入通话记录"""
    conn = get_conn()
    conn.executemany("""
        INSERT INTO call_records
        (record_id, evidence_id, caller_id, callee_id, call_time, duration)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [(
        r['record_id'],
        r['evidence_id'],
        r.get('caller_id'),
        r.get('callee_id'),
        r.get('call_time'),
        r.get('duration')
    ) for r in call_data])
    conn.commit()
    conn.close()


def insert_system_logs(log_data: list):
    """批量插入系统日志"""
    conn = get_conn()
    conn.executemany("""
        INSERT INTO system_logs
        (log_id, evidence_id, person_id, log_time, action, ip_address, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [(
        r['log_id'],
        r['evidence_id'],
        r.get('person_id'),
        r.get('log_time'),
        r.get('action'),
        r.get('ip_address'),
        r.get('details')
    ) for r in log_data])
    conn.commit()
    conn.close()
