"""证据导入模块 - 多格式数据导入"""
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import (
    create_evidence, link_person_evidence, get_conn,
    insert_statement, insert_chat_records, insert_document,
    insert_location_records, insert_call_records, insert_system_logs
)
from config import DATA_DIR


# ==================== 文件解析器 ====================

def parse_pdf(file_path: str) -> str:
    """解析PDF文件"""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        return text
    except Exception as e:
        return f"PDF解析失败: {str(e)}"


def parse_word(file_path: str) -> str:
    """解析Word文件"""
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        return f"Word解析失败: {str(e)}"


def parse_text(file_path: str) -> str:
    """解析纯文本文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except Exception as e:
            return f"文本解析失败: {str(e)}"


def parse_excel(file_path: str) -> pd.DataFrame:
    """解析Excel文件"""
    try:
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        raise ValueError(f"Excel解析失败: {str(e)}")


def extract_file_content(file_path: str) -> Tuple[str, pd.DataFrame]:
    """根据文件类型提取内容"""
    suffix = Path(file_path).suffix.lower()

    if suffix == '.pdf':
        return parse_pdf(file_path), None
    elif suffix in ['.doc', '.docx']:
        return parse_word(file_path), None
    elif suffix == '.txt':
        return parse_text(file_path), None
    elif suffix in ['.xls', '.xlsx']:
        return None, parse_excel(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")


# ==================== AI 识别接口（占位） ====================

def ai_classify_evidence(content: str = None, df: pd.DataFrame = None) -> dict:
    """
    AI识别证据类型和内容

    TODO: 集成实际的AI模型

    返回格式:
    {
        'evidence_type': '供述' | '证言' | '流水' | '聊天' | '文书' | '鉴定' | '笔录' | '测谎' | '轨迹' | '通话' | '日志' | '其他',
        'title': str,
        'event_time': str,
        'extract_time': str,
        'summary': str,
        'related_persons': [{'name': str, 'role': str}],
        'structured_data': dict | list  # 对于表格数据
    }
    """
    # ========== 占位实现：简单规则判断 ==========

    result = {
        'evidence_type': '其他',
        'title': '未命名证据',
        'event_time': None,
        'extract_time': None,
        'summary': '',
        'related_persons': [],
        'structured_data': None
    }

    # 如果是表格数据
    if df is not None:
        # 简单判断表格类型
        columns_str = '|'.join([str(c).lower() for c in df.columns])

        # 🔑 检测财付通格式 (27列，包含特征字段)
        tenpay_keywords = ['交易单号', '财付通', '用户id', '交易时间', '交易金额(分)', 'tenpay']
        tenpay_matches = sum(1 for kw in tenpay_keywords if kw in columns_str)

        if tenpay_matches >= 2 or len(df.columns) == 27:  # 财付通特征
            result['evidence_type'] = '流水'
            result['title'] = '财付通交易流水'
        elif any(k in columns_str for k in ['金额', '交易', '余额', 'amount', '收支']):
            result['evidence_type'] = '流水'
            result['title'] = '资金流水记录'
        elif any(k in columns_str for k in ['主叫', '被叫', '通话', 'caller', 'callee']):
            result['evidence_type'] = '通话'
            result['title'] = '通话记录'
        elif any(k in columns_str for k in ['经度', '纬度', 'lat', 'lng', '位置']):
            result['evidence_type'] = '轨迹'
            result['title'] = '行动轨迹'
        elif any(k in columns_str for k in ['时间', '操作', 'log', 'action', 'ip']):
            result['evidence_type'] = '日志'
            result['title'] = '系统操作日志'

        result['summary'] = f"包含 {len(df)} 条记录"
        result['structured_data'] = df.to_dict('records')

    # 如果是文本数据
    elif content:
        content_lower = content.lower()

        if '供述' in content or '承认' in content or '交代' in content:
            result['evidence_type'] = '供述'
            result['title'] = '犯罪嫌疑人供述'
        elif '证实' in content or '看到' in content or '听到' in content:
            result['evidence_type'] = '证言'
            result['title'] = '证人证言'
        elif '鉴定' in content or '检验' in content:
            result['evidence_type'] = '鉴定'
            result['title'] = '鉴定意见'
        elif '判决' in content or '裁定' in content:
            result['evidence_type'] = '文书'
            result['title'] = '司法文书'
        elif '笔录' in content:
            result['evidence_type'] = '笔录'
            result['title'] = '侦查笔录'
        elif '测谎' in content:
            result['evidence_type'] = '测谎'
            result['title'] = '测谎结果'

        result['summary'] = content[:200] + '...' if len(content) > 200 else content

    return result


def ai_extract_persons(content: str) -> List[Dict]:
    """
    从文本中提取人名

    TODO: 集成NER模型

    返回格式: [{'name': '张三', 'role': '嫌疑人'}, ...]
    """
    # ========== 占位实现：返回空列表 ==========
    return []


def _auto_extract_and_create_persons(df: pd.DataFrame, case_id: str, evidence_type: str = None):
    """
    从Excel数据中自动提取人员信息并创建persons记录

    Args:
        df: DataFrame数据
        case_id: 案件ID
        evidence_type: 证据类型（用于推断人员角色）
    """
    if df is None or df.empty:
        return

    # 根据不同证据类型提取不同的人员字段
    person_name_columns = []

    columns_str = '|'.join([str(c).lower() for c in df.columns])

    # 识别可能包含人名的列
    if '发送人' in df.columns:
        person_name_columns.append('发送人')
    if '接收人' in df.columns:
        person_name_columns.append('接收人')
    if '主叫方' in df.columns:
        person_name_columns.append('主叫方')
    if '被叫方' in df.columns:
        person_name_columns.append('被叫方')
    if '人员' in df.columns:
        person_name_columns.append('人员')
    if '用户' in df.columns:
        person_name_columns.append('用户')
    if '操作人' in df.columns:
        person_name_columns.append('操作人')

    # 提取所有人名（去重）
    person_names = set()
    for col in person_name_columns:
        if col in df.columns:
            names = df[col].dropna().unique()
            for name in names:
                name_str = str(name).strip()
                # 过滤无效名称
                if name_str and name_str != 'nan' and name_str != 'None' and len(name_str) > 0:
                    # 过滤时间戳格式（如 "2025-10-01 15:33:00"）
                    if not _is_timestamp_string(name_str):
                        person_names.add(name_str)

    if not person_names:
        return

    # 推断角色
    default_role = '涉案人'
    if evidence_type in ['供述', '辩解']:
        default_role = '嫌疑人'
    elif evidence_type == '证言':
        default_role = '证人'

    # 连接数据库
    conn = get_conn()
    cursor = conn.cursor()

    created_count = 0
    existing_count = 0

    for name in person_names:
        # 生成user_id（使用拼音或简化方式）
        user_id = _generate_user_id(name)

        # 检查是否已存在
        existing = cursor.execute(
            'SELECT COUNT(*) FROM persons WHERE user_id = ?',
            [user_id]
        ).fetchone()[0]

        if existing == 0:
            # 创建新人员记录
            try:
                cursor.execute('''
                    INSERT INTO persons (user_id, case_id, name, role)
                    VALUES (?, ?, ?, ?)
                ''', [user_id, case_id, name, default_role])
                created_count += 1
            except Exception as e:
                # 如果user_id冲突，尝试添加后缀
                for i in range(1, 10):
                    try:
                        cursor.execute('''
                            INSERT INTO persons (user_id, case_id, name, role)
                            VALUES (?, ?, ?, ?)
                        ''', [f"{user_id}{i:03d}", case_id, name, default_role])
                        created_count += 1
                        break
                    except:
                        continue
        else:
            existing_count += 1

    conn.commit()
    conn.close()

    if created_count > 0:
        print(f'  [自动提取] 创建了 {created_count} 个人员记录')
    if existing_count > 0:
        print(f'  [自动提取] {existing_count} 个人员已存在')


def _is_timestamp_string(s: str) -> bool:
    """
    判断字符串是否为时间戳格式

    Args:
        s: 待判断的字符串

    Returns:
        True if是时间戳，False otherwise
    """
    import re
    # 匹配常见的时间戳格式
    timestamp_patterns = [
        r'^\d{4}-\d{2}-\d{2}',  # 2025-10-01
        r'^\d{4}/\d{2}/\d{2}',  # 2025/10/01
        r'^\d{2}:\d{2}:\d{2}',  # 15:33:00
    ]
    return any(re.match(pattern, s) for pattern in timestamp_patterns)


def _generate_user_id(name: str) -> str:
    """
    根据姓名生成user_id

    Args:
        name: 姓名

    Returns:
        user_id字符串
    """
    import hashlib

    # 如果是常见姓名格式（2-4个汉字），尝试生成有意义的ID
    if 2 <= len(name) <= 4 and all('\u4e00' <= c <= '\u9fff' for c in name):
        try:
            from pypinyin import lazy_pinyin
            # 使用拼音生成ID
            pinyin_parts = lazy_pinyin(name)
            user_id = ''.join(pinyin_parts).lower()
            # 限制长度
            if len(user_id) > 20:
                user_id = user_id[:20]
            return user_id + "001"  # 添加后缀避免冲突
        except ImportError:
            pass

    # 如果是公司名称或其他，使用hash
    name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
    # 尝试提取首字母或前几个字符
    short_name = name[:4] if len(name) <= 10 else name[:2]
    return f"{short_name}_{name_hash}"


# ==================== 证据导入主流程 ====================

def import_evidence(
    file_path: str,
    case_id: str,
    manual_info: dict = None
) -> dict:
    """
    导入证据文件

    Args:
        file_path: 文件路径
        case_id: 案件ID
        manual_info: 用户手动提供的信息（可选）
            {
                'evidence_type': str,
                'title': str,
                'related_persons': [person_id, ...],
                'event_time': str,
                'extract_time': str
            }

    Returns:
        {
            'success': bool,
            'evidence_id': str,
            'evidence_type': str,
            'message': str
        }
    """
    try:
        # 1. 提取文件内容
        text_content, df_content = extract_file_content(file_path)

        # 2. AI识别证据类型和内容（或使用手动信息）
        if manual_info and manual_info.get('evidence_type'):
            ai_result = manual_info
        else:
            ai_result = ai_classify_evidence(content=text_content, df=df_content)

        # 2.5. 【新增】自动从Excel中提取人员信息并创建persons记录
        if df_content is not None:
            _auto_extract_and_create_persons(df_content, case_id, ai_result.get('evidence_type'))

        # 3. 生成证据ID
        evidence_id = str(uuid.uuid4())

        # 4. 保存原始文件
        file_name = Path(file_path).name
        save_dir = DATA_DIR / "evidence_files" / case_id
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{evidence_id}_{file_name}"

        # 复制文件到证据目录
        import shutil
        shutil.copy2(file_path, save_path)

        # 5. 创建证据元数据
        evidence_data = {
            'evidence_id': evidence_id,
            'case_id': case_id,
            'evidence_type': ai_result.get('evidence_type', '其他'),
            'title': ai_result.get('title', file_name),
            'file_path': str(save_path),
            'event_time': ai_result.get('event_time'),
            'extract_time': ai_result.get('extract_time'),
            'ai_summary': ai_result.get('summary', ''),
            'status': '已分类' if ai_result.get('evidence_type') != '其他' else '待审核'
        }

        create_evidence(evidence_data)

        # 6. 先关联人员（供述/证言需要person_id）
        related_persons = manual_info.get('related_persons', []) if manual_info else []
        if not related_persons and text_content:
            # AI提取人名并匹配
            extracted_persons = ai_extract_persons(text_content)
            related_persons = _match_persons_to_db(extracted_persons, case_id)

        for person_id in related_persons:
            link_person_evidence(person_id, evidence_id, '当事人')

        # 7. 根据证据类型存入具体表
        evidence_type = evidence_data['evidence_type']

        if evidence_type in ['供述', '辩解', '证言']:
            _import_statement(evidence_id, text_content, ai_result)

        elif evidence_type == '流水':
            _import_financial_records(evidence_id, case_id, df_content)

        elif evidence_type == '聊天':
            data = df_content if df_content is not None else text_content
            _import_chat_records(evidence_id, data)

        elif evidence_type == '通话':
            _import_call_records(evidence_id, df_content)

        elif evidence_type == '轨迹':
            _import_location_records(evidence_id, df_content)

        elif evidence_type == '日志':
            _import_system_logs(evidence_id, df_content)

        elif evidence_type in ['文书', '鉴定', '笔录', '测谎']:
            _import_document(evidence_id, text_content, evidence_type)

        return {
            'success': True,
            'evidence_id': evidence_id,
            'evidence_type': evidence_type,
            'message': f'成功导入{evidence_type}证据'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'导入失败: {str(e)}'
        }


# ==================== 各类型证据的导入逻辑 ====================

def _import_statement(evidence_id: str, content: str, ai_result: dict):
    """导入供述/证言"""
    statement_id = str(uuid.uuid4())

    # 从关联的人员中获取第一个person_id（如果有的话）
    conn = get_conn()
    person_id = conn.execute(
        "SELECT person_id FROM person_evidence_relation WHERE evidence_id = ? LIMIT 1",
        [evidence_id]
    ).fetchone()
    conn.close()

    person_id = person_id[0] if person_id else None

    insert_statement({
        'statement_id': statement_id,
        'evidence_id': evidence_id,
        'person_id': person_id,  # 从关联表获取
        'statement_type': ai_result.get('evidence_type'),
        'content': content,
        'key_persons': json.dumps(ai_result.get('key_persons', []), ensure_ascii=False),
        'key_amounts': json.dumps(ai_result.get('key_amounts', []), ensure_ascii=False),
        'key_events': json.dumps(ai_result.get('key_events', []), ensure_ascii=False)
    })


def _import_financial_records(evidence_id: str, case_id: str, df: pd.DataFrame):
    """导入资金流水到transactions表"""
    if df is None or df.empty:
        return

    conn = get_conn()

    # 🔑 检测是否为财付通格式（27列）
    is_tenpay = len(df.columns) == 27

    if is_tenpay:
        # 财付通格式：使用固定列索引
        from src.ingest import TRADE_COLS, parse_trades_xls, parse_reginfo_xls

        # 统一列名
        df.columns = TRADE_COLS

        # 调用财付通专用导入逻辑
        _import_tenpay_transactions(evidence_id, case_id, df, conn)
    else:
        # 通用流水格式：智能列名映射
        column_mapping = _smart_column_mapping(df.columns, {
            'user_id': ['账号', '用户id', 'userid', 'user_id', '用户账号'],
            'user_name': ['姓名', '用户名', 'name', '账户名'],
            'trade_time': ['交易时间', '时间', 'time', 'date', '日期'],
            'amount': ['金额', '交易金额', 'amount', '数额'],
            'counterpart_name': ['对方', '交易对方', '对手方', 'counterpart'],
            'direction': ['收支', '方向', 'direction', '类型'],
            'purpose': ['用途', '备注', 'purpose', 'remark'],
        })
        _import_generic_transactions(evidence_id, case_id, df, column_mapping, conn)

    conn.close()


def _import_tenpay_transactions(evidence_id: str, case_id: str, df: pd.DataFrame, conn):
    """导入财付通交易数据（复用ingest.py逻辑）"""
    # 清洗数据
    df["user_id"] = df["user_id"].ffill()
    df["user_account_name"] = df["user_account_name"].ffill()
    df = df.dropna(subset=["user_id"])
    df["trade_time"] = pd.to_datetime(df["trade_time"], errors="coerce")
    df = df.dropna(subset=["trade_time"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0).astype(int).abs()
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce").fillna(0).astype(int)
    df["direction"] = df["direction"].astype(str).str.strip()

    # 清洗对手方信息
    import re
    def _clean_counterpart_id(raw: str) -> str:
        if pd.isna(raw) or raw == "":
            return ""
        s = str(raw)
        m = re.search(r'\(([^)]+)\)$', s)
        if m:
            return m.group(1)
        return s

    def _clean_counterpart_name(raw_name, raw_id) -> str:
        if pd.notna(raw_name) and str(raw_name).strip():
            return str(raw_name).strip()
        if pd.isna(raw_id):
            return ""
        s = str(raw_id)
        m = re.match(r'^(.+?)\(', s)
        if m:
            return m.group(1)
        return ""

    df["counterpart_name_clean"] = df.apply(
        lambda r: _clean_counterpart_name(r["counterpart_account"], r["counterpart_id"]),
        axis=1
    )
    df["counterpart_id_clean"] = df["counterpart_id"].apply(_clean_counterpart_id)

    # 自动创建用户
    for user_id in df["user_id"].unique():
        user_row = df[df["user_id"] == user_id].iloc[0]
        user_name = str(user_row["user_account_name"])

        exists = conn.execute("SELECT 1 FROM persons WHERE user_id = ?", [user_id]).fetchone()
        if not exists:
            conn.execute("""
                INSERT INTO persons (user_id, case_id, name, role)
                VALUES (?, ?, ?, ?)
            """, [user_id, case_id, user_name, '涉案人'])

    conn.commit()

    # 插入交易记录
    for _, row in df.iterrows():
        conn.execute("""
            INSERT INTO transactions
            (case_id, evidence_id, trade_no, big_trade_no, user_id, user_name, direction,
             biz_type, purpose, trade_time, amount, balance, user_card,
             counterpart_id, counterpart_name, counterpart_card, counterpart_bank,
             remark, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            case_id, evidence_id,
            str(row["trade_no"]), str(row["big_trade_no"]),
            str(row["user_id"]), str(row["user_account_name"]),
            str(row["direction"]), str(row["biz_type"]), str(row["purpose"]),
            str(row["trade_time"]), int(row["amount"]), int(row["balance"]),
            str(row["user_card"]) if pd.notna(row["user_card"]) else None,
            row["counterpart_id_clean"], row["counterpart_name_clean"],
            str(row["counterpart_card"]) if pd.notna(row["counterpart_card"]) else None,
            str(row["counterpart_bank"]) if pd.notna(row["counterpart_bank"]) else None,
            str(row.get("remark1", "")) if pd.notna(row.get("remark1")) else None,
            '财付通'
        ])

    conn.commit()


def _import_generic_transactions(evidence_id: str, case_id: str, df: pd.DataFrame, column_mapping: dict, conn):
    """导入通用格式交易数据"""

    # 自动创建不存在的人员
    user_ids_in_data = set()
    for _, row in df.iterrows():
        user_id = str(row.get(column_mapping.get('user_id', 'user_id'), ''))
        user_name = str(row.get(column_mapping.get('user_name', 'user_name'), ''))
        if user_id and user_id not in user_ids_in_data:
            user_ids_in_data.add(user_id)
            # 检查是否存在
            exists = conn.execute("SELECT 1 FROM persons WHERE user_id = ?", [user_id]).fetchone()
            if not exists:
                # 自动创建
                conn.execute("""
                    INSERT INTO persons (user_id, case_id, name, role)
                    VALUES (?, ?, ?, ?)
                """, [user_id, case_id, user_name, '涉案人'])

    conn.commit()

    # 插入交易记录
    for _, row in df.iterrows():
        amount_val = row.get(column_mapping.get('amount', 'amount'), 0)
        # 转换为分
        if isinstance(amount_val, str):
            amount_val = float(amount_val.replace(',', '').replace('¥', ''))
        amount_fen = int(float(amount_val) * 100)

        direction = row.get(column_mapping.get('direction', 'direction'), '')
        if '入' in str(direction) or '收' in str(direction):
            direction = '入'
        elif '出' in str(direction) or '支' in str(direction):
            direction = '出'

        user_id = str(row.get(column_mapping.get('user_id', 'user_id'), ''))

        conn.execute("""
            INSERT INTO transactions
            (case_id, evidence_id, user_id, user_name, trade_time, amount, direction,
             counterpart_name, purpose, source_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            case_id,
            evidence_id,
            user_id,
            str(row.get(column_mapping.get('user_name', 'user_name'), '')),
            str(row.get(column_mapping.get('trade_time', 'trade_time'), '')),
            amount_fen,
            direction,
            str(row.get(column_mapping.get('counterpart_name', 'counterpart_name'), '')),
            str(row.get(column_mapping.get('purpose', 'purpose'), '')),
            '其他银行'  # 区别于原有的财付通数据
        ])

    conn.commit()


def _import_chat_records(evidence_id: str, data):
    """导入聊天记录"""
    chat_list = []

    if isinstance(data, pd.DataFrame):
        # 获取人名到ID的映射
        conn = get_conn()
        name_to_id = {}
        persons = conn.execute("SELECT user_id, name FROM persons").fetchall()
        for user_id, name in persons:
            if name:
                name_to_id[name] = user_id
        conn.close()

        # Excel格式的聊天记录
        for idx, row in data.iterrows():
            sender_name = str(row.get('发送人', ''))
            receiver_name = str(row.get('接收人', ''))

            # 尝试映射到user_id，如果找不到则设为None
            sender_id = name_to_id.get(sender_name) if sender_name in name_to_id else None
            receiver_id = name_to_id.get(receiver_name) if receiver_name in name_to_id else None

            chat_list.append({
                'message_id': f"{evidence_id}_{idx}",
                'evidence_id': evidence_id,
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'send_time': str(row.get('时间', '')),
                'content': str(row.get('内容', '')),
                'message_type': str(row.get('类型', '文本'))
            })
    else:
        # 文本格式的聊天记录（简单解析）
        # TODO: 更复杂的文本聊天记录解析
        pass

    if chat_list:
        insert_chat_records(chat_list)


def _import_call_records(evidence_id: str, df: pd.DataFrame):
    """导入通话记录"""
    if df is None or df.empty:
        return

    # 获取人名到ID的映射
    conn = get_conn()
    name_to_id = {}
    persons = conn.execute("SELECT user_id, name FROM persons").fetchall()
    for user_id, name in persons:
        if name:
            name_to_id[name] = user_id
    conn.close()

    column_mapping = _smart_column_mapping(df.columns, {
        'caller_id': ['主叫', 'caller', '拨打方'],
        'callee_id': ['被叫', 'callee', '接听方'],
        'call_time': ['时间', 'time', '通话时间'],
        'duration': ['时长', 'duration', '通话时长']
    })

    call_list = []
    for idx, row in df.iterrows():
        duration = row.get(column_mapping.get('duration', 'duration'), 0)
        if isinstance(duration, str):
            # 可能是 "1分30秒" 格式
            duration = _parse_duration(duration)

        caller_name = str(row.get(column_mapping.get('caller_id', 'caller_id'), ''))
        callee_name = str(row.get(column_mapping.get('callee_id', 'callee_id'), ''))

        # 尝试映射到user_id，如果找不到则设为None
        caller_id = name_to_id.get(caller_name) if caller_name in name_to_id else None
        callee_id = name_to_id.get(callee_name) if callee_name in name_to_id else None

        call_list.append({
            'record_id': f"{evidence_id}_{idx}",
            'evidence_id': evidence_id,
            'caller_id': caller_id,
            'callee_id': callee_id,
            'call_time': str(row.get(column_mapping.get('call_time', 'call_time'), '')),
            'duration': int(duration)
        })

    insert_call_records(call_list)


def _import_location_records(evidence_id: str, df: pd.DataFrame):
    """导入轨迹数据"""
    if df is None or df.empty:
        return

    # 获取人名到ID的映射
    conn = get_conn()
    name_to_id = {}
    persons = conn.execute("SELECT user_id, name FROM persons").fetchall()
    for user_id, name in persons:
        if name:
            name_to_id[name] = user_id
    conn.close()

    column_mapping = _smart_column_mapping(df.columns, {
        'person_id': ['人员', 'person', '用户'],
        'record_time': ['时间', 'time'],
        'latitude': ['纬度', 'lat', 'latitude'],
        'longitude': ['经度', 'lng', 'lon', 'longitude'],
        'location_name': ['位置', 'location', '地点']
    })

    location_list = []
    for idx, row in df.iterrows():
        person_name = str(row.get(column_mapping.get('person_id', 'person_id'), ''))
        person_id = name_to_id.get(person_name) if person_name in name_to_id else None

        location_list.append({
            'record_id': f"{evidence_id}_{idx}",
            'evidence_id': evidence_id,
            'person_id': person_id,
            'record_time': str(row.get(column_mapping.get('record_time', 'record_time'), '')),
            'latitude': float(row.get(column_mapping.get('latitude', 'latitude'), 0)),
            'longitude': float(row.get(column_mapping.get('longitude', 'longitude'), 0)),
            'location_name': str(row.get(column_mapping.get('location_name', 'location_name'), ''))
        })

    insert_location_records(location_list)


def _import_system_logs(evidence_id: str, df: pd.DataFrame):
    """导入系统日志"""
    if df is None or df.empty:
        return

    # 获取人名到ID的映射
    conn = get_conn()
    name_to_id = {}
    persons = conn.execute("SELECT user_id, name FROM persons").fetchall()
    for user_id, name in persons:
        if name:
            name_to_id[name] = user_id
    conn.close()

    column_mapping = _smart_column_mapping(df.columns, {
        'person_id': ['用户', 'user', '操作人'],
        'log_time': ['时间', 'time'],
        'action': ['操作', 'action', '行为'],
        'ip_address': ['ip', 'ip地址', 'ip_address'],
        'details': ['详情', 'details', '描述']
    })

    log_list = []
    for idx, row in df.iterrows():
        person_name = str(row.get(column_mapping.get('person_id', 'person_id'), ''))
        person_id = name_to_id.get(person_name) if person_name in name_to_id else None

        log_list.append({
            'log_id': f"{evidence_id}_{idx}",
            'evidence_id': evidence_id,
            'person_id': person_id,
            'log_time': str(row.get(column_mapping.get('log_time', 'log_time'), '')),
            'action': str(row.get(column_mapping.get('action', 'action'), '')),
            'ip_address': str(row.get(column_mapping.get('ip_address', 'ip_address'), '')),
            'details': str(row.get(column_mapping.get('details', 'details'), ''))
        })

    insert_system_logs(log_list)


def _import_document(evidence_id: str, content: str, doc_type: str):
    """导入文书类证据"""
    doc_id = str(uuid.uuid4())
    insert_document({
        'doc_id': doc_id,
        'evidence_id': evidence_id,
        'doc_subtype': doc_type,
        'content': content,
        'key_info': '{}'  # TODO: AI提取关键信息
    })


# ==================== 辅助函数 ====================

def _smart_column_mapping(columns: list, target_mapping: dict) -> dict:
    """智能列名映射"""
    result = {}
    columns_lower = [str(c).lower() for c in columns]

    for target_col, possible_names in target_mapping.items():
        for possible in possible_names:
            for i, col in enumerate(columns_lower):
                if possible.lower() in col:
                    result[target_col] = columns[i]
                    break
            if target_col in result:
                break

    return result


def _parse_duration(duration_str: str) -> int:
    """解析时长字符串为秒数"""
    try:
        if '分' in duration_str and '秒' in duration_str:
            parts = duration_str.replace('分', ':').replace('秒', '').split(':')
            return int(parts[0]) * 60 + int(parts[1])
        elif '分' in duration_str:
            return int(duration_str.replace('分', '')) * 60
        elif '秒' in duration_str:
            return int(duration_str.replace('秒', ''))
        else:
            return int(duration_str)
    except:
        return 0


def _match_persons_to_db(extracted_persons: List[Dict], case_id: str) -> List[str]:
    """将提取的人名匹配到数据库中的person_id"""
    if not extracted_persons:
        return []

    conn = get_conn()
    matched_ids = []

    for person in extracted_persons:
        name = person.get('name')
        if not name:
            continue

        result = conn.execute(
            "SELECT user_id FROM persons WHERE case_id = ? AND name = ?",
            [case_id, name]
        ).fetchone()

        if result:
            matched_ids.append(result[0])

    conn.close()
    return matched_ids
