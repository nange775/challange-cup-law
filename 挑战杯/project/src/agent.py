"""AI 智能侦查 Agent """
import json
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_PROVIDERS, get_provider_api_key
from src.database import (
    get_all_persons, get_person_transactions, get_all_transactions,
    get_counterpart_summary, get_db_stats, get_bank_cards,
    get_all_cases, get_case_evidences, get_person_evidences, get_conn
)
from src.anomaly import (
    run_all_detections, get_risk_summary,
    detect_structuring, detect_abnormal_time, detect_wealth_surge,
    detect_large_transfers, detect_high_freq_counterpart
)
from src.graph_analysis import build_transaction_graph, find_bridge_accounts, find_fund_cycles, get_network_metrics, get_top_counterparts
from src.profiler import generate_profile, generate_report_text


# ============================================================
# 工具定义 (Anthropic 格式, OpenAI 格式自动转换)
# ============================================================

TOOLS_ANTHROPIC = [
    {
        "name": "query_persons",
        "description": "查询数据库中所有已录入人员的基本信息,包括姓名、身份证号、账号、手机号等。用于了解当前有哪些调查对象。",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "query_db_stats",
        "description": "查询数据库整体统计: 人员数、银行卡数、交易记录数。",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "query_transactions",
        "description": "查询指定用户的交易记录。可按方向(入/出)、用途(转账/消费/提现)、时间范围筛选。返回交易明细。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
                "direction": {"type": "string", "description": "筛选方向: 入 或 出, 留空为全部", "enum": ["入", "出", ""]},
                "purpose": {"type": "string", "description": "筛选用途: 转账/消费/提现等, 留空为全部"},
                "start_date": {"type": "string", "description": "起始日期 YYYY-MM-DD, 留空不限"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD, 留空不限"},
                "limit": {"type": "integer", "description": "返回最多多少条, 默认50"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_counterparts",
        "description": "查询指定用户的对手方汇总: 每个对手方的交易笔数、总入账、总出账、首末交易时间。用于发现可疑关系人。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
                "top_n": {"type": "integer", "description": "返回前N个对手方, 默认20"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "run_anomaly_detection",
        "description": "对指定用户执行全套异常检测算法, 包括: 化整为零、深夜交易、财富突增、高频对手方、大额转账。返回所有检测结果和风险摘要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "analyze_network",
        "description": "分析指定用户的资金关系网络: 网络指标、过桥账户(白手套)检测、资金回流环路检测、关键关系人排名。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "generate_full_profile",
        "description": "生成指定用户的完整画像报告, 包含基本信息、资金概况、异常检测、关系网络、风险评级和侦查建议。这是最全面的分析工具。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "search_specific_counterpart",
        "description": "查询指定用户与某个特定对手方之间的所有交易明细。用于深入调查特定关系。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名, 如 jerry123 或 李四"},
                "counterpart_name": {"type": "string", "description": "对手方姓名关键词"},
            },
            "required": ["user_id", "counterpart_name"],
        }
    },
    {
        "name": "query_counterparts_by_type",
        "description": "按对手方类型(企业/个人)查询交易汇总。用于分析用户与企业或个人之间的资金往来。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "counterpart_type": {"type": "string", "description": "对手方类型: enterprise(企业) 或 person(个人)", "enum": ["enterprise", "person"]},
                "top_n": {"type": "integer", "description": "返回前N个, 默认20"},
            },
            "required": ["user_id", "counterpart_type"],
        }
    },
    {
        "name": "query_cases",
        "description": "查询数据库中所有案件的基本信息，包括案件ID、案件名称、创建时间等。",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "query_case_evidences",
        "description": "查询指定案件的所有证据列表，包括证据类型、标题、上传时间、AI摘要等。用于了解案件有哪些证据材料。",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "案件ID，如 CASE_LIJIAN_2025"},
            },
            "required": ["case_id"],
        }
    },
    {
        "name": "query_person_evidences",
        "description": "查询指定人员相关的所有证据列表，包括供述、证言、聊天记录、通话记录等。用于全面了解某人涉及的证据材料。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名，如 lijian001 或 李建"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_chat_records",
        "description": "查询指定人员的聊天记录详情，可以筛选聊天对象和时间范围。用于分析沟通内容和隐喻暗语。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "other_person": {"type": "string", "description": "对方姓名（可选），用于查询两人之间的聊天"},
                "limit": {"type": "integer", "description": "返回最多多少条，默认50"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_call_records",
        "description": "查询指定人员的通话记录，包括主叫、被叫、通话时间、时长。用于分析通话频率和联系关系。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "limit": {"type": "integer", "description": "返回最多多少条，默认50"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_location_records",
        "description": "查询指定人员的行动轨迹记录，包括时间、经纬度、位置名称。用于分析活动轨迹和碰撞分析。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "limit": {"type": "integer", "description": "返回最多多少条，默认50"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_system_logs",
        "description": "查询指定人员的系统操作日志，包括登录、修改、删除等操作记录。用于分析异常操作行为。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "action": {"type": "string", "description": "操作类型（可选），如：登录/修改/删除"},
                "limit": {"type": "integer", "description": "返回最多多少条，默认50"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_statements",
        "description": "查询指定人员的供述、辩解或证言笔录内容。用于了解口供内容和矛盾之处。",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "用户ID或姓名"},
                "statement_type": {"type": "string", "description": "类型（可选）：供述/辩解/证言"},
            },
            "required": ["user_id"],
        }
    },
    {
        "name": "query_documents",
        "description": "查询指定案件的文书类证据，包括：起诉书、判决书等司法文书，鉴定意见（含测谎报告、笔迹鉴定等），辨认笔录等。用于获取结论性意见和专业分析。注意：测谎报告归类在\"鉴定\"类型下。",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "案件ID"},
                "doc_subtype": {"type": "string", "description": "文书子类型（可选）：文书（起诉书/判决书）/鉴定（测谎报告/笔迹鉴定等）/笔录（辨认笔录等）"},
            },
            "required": ["case_id"],
        }
    },
    {
        "name": "query_evidence_content",
        "description": "查询指定证据的完整原文内容。当其他工具只返回摘要时，使用此工具获取证据全文。",
        "input_schema": {
            "type": "object",
            "properties": {
                "evidence_id": {"type": "string", "description": "证据ID（从其他查询工具的结果中获取）"},
            },
            "required": ["evidence_id"],
        }
    },
    {
        "name": "generate_investigation_profile",
        "description": "生成完整的检察侦查画像报告。基于案件全部证据数据（聊天记录、通话记录、轨迹数据、系统日志、资金流水、供述笔录等），生成包含心理底色、异常交往人员、资金漏斗、审讯突破策略四大模块的专业侦查报告。",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "案件ID"},
                "user_id": {"type": "string", "description": "目标人物ID或姓名"},
            },
            "required": ["case_id", "user_id"],
        }
    },
]


def _to_openai_tools(anthropic_tools: list) -> list:
    """将 Anthropic 工具格式转换为 OpenAI 工具格式"""
    openai_tools = []
    for t in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
        })
    return openai_tools


TOOLS_OPENAI = _to_openai_tools(TOOLS_ANTHROPIC)


# ============================================================
# 姓名 -> user_id 自动解析
# ============================================================

def _resolve_user_id(user_id_or_name: str) -> str:
    """
    智能解析: 输入可能是 user_id (如 jerry123) 或姓名 (如 李四)。
    优先精确匹配 user_id, 再模糊匹配姓名。
    """
    if not user_id_or_name:
        return user_id_or_name

    persons = get_all_persons()
    if persons.empty:
        return user_id_or_name

    # 精确匹配 user_id
    match = persons[persons["user_id"] == user_id_or_name]
    if not match.empty:
        return match.iloc[0]["user_id"]

    # 精确匹配姓名
    match = persons[persons["name"] == user_id_or_name]
    if not match.empty:
        return match.iloc[0]["user_id"]

    # 模糊匹配姓名
    match = persons[persons["name"].str.contains(user_id_or_name, na=False)]
    if not match.empty:
        return match.iloc[0]["user_id"]

    return user_id_or_name


# ============================================================
# 工具执行器 (与厂商无关)
# ============================================================

def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """执行工具调用, 返回JSON字符串结果"""
    # 所有含 user_id 参数的工具, 自动支持姓名输入
    if "user_id" in tool_input:
        tool_input["user_id"] = _resolve_user_id(tool_input["user_id"])

    try:
        if tool_name == "query_persons":
            df = get_all_persons()
            return df.to_json(orient="records", force_ascii=False)

        elif tool_name == "query_db_stats":
            stats = get_db_stats()
            return json.dumps(stats, ensure_ascii=False)

        elif tool_name == "query_transactions":
            user_id = tool_input["user_id"]
            df = get_person_transactions(user_id)
            if df.empty:
                return json.dumps({"message": f"未找到用户 {user_id} 的交易记录"}, ensure_ascii=False)

            direction = tool_input.get("direction", "")
            if direction:
                df = df[df["direction"] == direction]

            purpose = tool_input.get("purpose", "")
            if purpose:
                df = df[df["purpose"].str.contains(purpose, na=False)]

            start_date = tool_input.get("start_date", "")
            if start_date:
                df = df[df["trade_time"] >= start_date]

            end_date = tool_input.get("end_date", "")
            if end_date:
                df = df[df["trade_time"] <= end_date]

            limit = tool_input.get("limit", 50)
            total_count = len(df)
            df = df.head(limit)
            df["trade_time"] = df["trade_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
            df["amount_yuan"] = df["amount"] / 100
            cols = ["trade_time", "direction", "purpose", "amount_yuan", "counterpart_name", "remark"]
            records = json.loads(df[cols].to_json(orient="records", force_ascii=False))
            return json.dumps({
                "说明": f"共{total_count}条记录,返回前{len(records)}条。请严格基于这些数据回答,不要编造不在列表中的交易记录。",
                "data": records,
            }, ensure_ascii=False)

        elif tool_name == "query_counterparts":
            user_id = tool_input["user_id"]
            top_n = tool_input.get("top_n", 20)
            df = get_counterpart_summary(user_id)
            if df.empty:
                return json.dumps({"message": "无对手方数据"}, ensure_ascii=False)
            result = df.head(top_n)
            records = json.loads(result.to_json(orient="records", force_ascii=False))
            return json.dumps({
                "说明": f"以下是该用户的前{len(records)}个对手方汇总(按交易笔数排序),请严格基于此数据回答,不要编造不在列表中的交易",
                "data": records,
            }, ensure_ascii=False)

        elif tool_name == "run_anomaly_detection":
            user_id = tool_input["user_id"]
            tx = get_person_transactions(user_id)
            if tx.empty:
                return json.dumps({"message": "无交易数据"}, ensure_ascii=False)
            results = run_all_detections(tx)
            summary = get_risk_summary(results)
            output = {"risk_summary": summary}
            for key, df in results.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    output[key + "_count"] = len(df)
            return json.dumps(output, ensure_ascii=False, default=str)

        elif tool_name == "analyze_network":
            user_id = tool_input["user_id"]
            tx = get_person_transactions(user_id)
            if tx.empty:
                return json.dumps({"message": "无交易数据"}, ensure_ascii=False)
            persons = get_all_persons()
            person_row = persons[persons["user_id"] == user_id]
            target_name = person_row.iloc[0]["name"] if not person_row.empty else user_id

            G = build_transaction_graph(tx)
            metrics = get_network_metrics(G, target_name)
            bridges = find_bridge_accounts(G, target_name)
            cycles = find_fund_cycles(G, target_name)
            top = get_top_counterparts(G, target_name)
            return json.dumps({
                "network_metrics": metrics,
                "bridge_accounts": bridges[:10],
                "fund_cycles": cycles[:10],
                "top_counterparts": top,
            }, ensure_ascii=False, default=str)

        elif tool_name == "generate_full_profile":
            user_id = tool_input["user_id"]
            profile = generate_profile(user_id)
            report = generate_report_text(profile)
            return report

        elif tool_name == "query_counterparts_by_type":
            user_id = tool_input["user_id"]
            cp_type = tool_input["counterpart_type"]
            top_n = tool_input.get("top_n", 20)
            df = get_counterpart_summary(user_id)
            if df.empty:
                return json.dumps({"message": "无对手方数据"}, ensure_ascii=False)
            # 按类型筛选: 企业名通常含"公司/有限/科技/银联/股份"等
            enterprise_keywords = ["公司", "有限", "银联", "财付通", "科技", "管理", "股份", "银行", "集团", "商业", "服务"]
            is_enterprise = df["counterpart_name"].apply(
                lambda name: any(kw in str(name) for kw in enterprise_keywords)
            )
            if cp_type == "enterprise":
                filtered = df[is_enterprise]
            else:
                filtered = df[~is_enterprise]
            if filtered.empty:
                type_label = "企业" if cp_type == "enterprise" else "个人"
                return json.dumps({"message": f"未找到与{type_label}的交易记录"}, ensure_ascii=False)
            return filtered.head(top_n).to_json(orient="records", force_ascii=False)

        elif tool_name == "search_specific_counterpart":
            user_id = tool_input["user_id"]
            cp_name = tool_input["counterpart_name"]
            tx = get_person_transactions(user_id)
            if tx.empty:
                return json.dumps({"message": "无交易数据"}, ensure_ascii=False)
            matched = tx[tx["counterpart_name"].str.contains(cp_name, na=False)]
            if matched.empty:
                return json.dumps({"message": f"未找到与「{cp_name}」相关的交易"}, ensure_ascii=False)
            matched["trade_time"] = matched["trade_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
            matched["amount_yuan"] = matched["amount"] / 100
            cols = ["trade_time", "direction", "purpose", "amount_yuan", "counterpart_name", "remark"]
            return matched[cols].to_json(orient="records", force_ascii=False)

        # ========== 新增：证据系统查询工具 ==========

        elif tool_name == "query_cases":
            df = get_all_cases()
            if df.empty:
                return json.dumps({"message": "暂无案件数据"}, ensure_ascii=False)
            return df.to_json(orient="records", force_ascii=False)

        elif tool_name == "query_case_evidences":
            case_id = tool_input["case_id"]
            df = get_case_evidences(case_id)
            if df.empty:
                return json.dumps({"message": f"案件 {case_id} 无证据记录"}, ensure_ascii=False)
            return df.to_json(orient="records", force_ascii=False)

        elif tool_name == "query_person_evidences":
            user_id = tool_input["user_id"]
            df = get_person_evidences(user_id)
            if df.empty:
                return json.dumps({"message": f"未找到用户 {user_id} 相关的证据"}, ensure_ascii=False)
            return df.to_json(orient="records", force_ascii=False)

        elif tool_name == "query_chat_records":
            user_id = tool_input["user_id"]
            limit = tool_input.get("limit", 50)
            other_person = tool_input.get("other_person", "")

            conn = get_conn()
            if other_person:
                # 解析对方user_id
                other_id = _resolve_user_id(other_person)
                query = """
                    SELECT * FROM chat_records
                    WHERE (sender_id = ? AND receiver_id = ?)
                       OR (sender_id = ? AND receiver_id = ?)
                    ORDER BY send_time DESC LIMIT ?
                """
                df = pd.read_sql(query, conn, params=[user_id, other_id, other_id, user_id, limit])
            else:
                query = """
                    SELECT * FROM chat_records
                    WHERE sender_id = ? OR receiver_id = ?
                    ORDER BY send_time DESC LIMIT ?
                """
                df = pd.read_sql(query, conn, params=[user_id, user_id, limit])
            conn.close()

            if df.empty:
                return json.dumps({"message": "未找到聊天记录"}, ensure_ascii=False)
            return json.dumps({
                "说明": f"共找到{len(df)}条聊天记录",
                "data": json.loads(df.to_json(orient="records", force_ascii=False))
            }, ensure_ascii=False)

        elif tool_name == "query_call_records":
            user_id = tool_input["user_id"]
            limit = tool_input.get("limit", 50)

            conn = get_conn()
            query = """
                SELECT * FROM call_records
                WHERE caller_id = ? OR callee_id = ?
                ORDER BY call_time DESC LIMIT ?
            """
            df = pd.read_sql(query, conn, params=[user_id, user_id, limit])
            conn.close()

            if df.empty:
                return json.dumps({"message": "未找到通话记录"}, ensure_ascii=False)
            return json.dumps({
                "说明": f"共找到{len(df)}条通话记录",
                "data": json.loads(df.to_json(orient="records", force_ascii=False))
            }, ensure_ascii=False)

        elif tool_name == "query_location_records":
            user_id = tool_input["user_id"]
            limit = tool_input.get("limit", 50)

            conn = get_conn()
            query = """
                SELECT * FROM location_records
                WHERE person_id = ?
                ORDER BY record_time DESC LIMIT ?
            """
            df = pd.read_sql(query, conn, params=[user_id, limit])
            conn.close()

            if df.empty:
                return json.dumps({"message": "未找到轨迹记录"}, ensure_ascii=False)
            return json.dumps({
                "说明": f"共找到{len(df)}条轨迹记录",
                "data": json.loads(df.to_json(orient="records", force_ascii=False))
            }, ensure_ascii=False)

        elif tool_name == "query_system_logs":
            user_id = tool_input["user_id"]
            limit = tool_input.get("limit", 50)
            action = tool_input.get("action", "")

            conn = get_conn()
            if action:
                query = """
                    SELECT * FROM system_logs
                    WHERE person_id = ? AND action LIKE ?
                    ORDER BY log_time DESC LIMIT ?
                """
                df = pd.read_sql(query, conn, params=[user_id, f"%{action}%", limit])
            else:
                query = """
                    SELECT * FROM system_logs
                    WHERE person_id = ?
                    ORDER BY log_time DESC LIMIT ?
                """
                df = pd.read_sql(query, conn, params=[user_id, limit])
            conn.close()

            if df.empty:
                return json.dumps({"message": "未找到系统日志"}, ensure_ascii=False)
            return json.dumps({
                "说明": f"共找到{len(df)}条操作日志",
                "data": json.loads(df.to_json(orient="records", force_ascii=False))
            }, ensure_ascii=False)

        elif tool_name == "query_statements":
            user_id = tool_input["user_id"]
            statement_type = tool_input.get("statement_type", "")

            conn = get_conn()

            # 方式1：通过person_id直接查询
            if statement_type:
                query1 = """
                    SELECT s.*, e.title, e.upload_time
                    FROM statements s
                    JOIN evidence_meta e ON s.evidence_id = e.evidence_id
                    WHERE s.person_id = ? AND s.statement_type = ?
                """
                df = pd.read_sql(query1, conn, params=[user_id, statement_type])
            else:
                query1 = """
                    SELECT s.*, e.title, e.upload_time
                    FROM statements s
                    JOIN evidence_meta e ON s.evidence_id = e.evidence_id
                    WHERE s.person_id = ?
                """
                df = pd.read_sql(query1, conn, params=[user_id])

            # 方式2：如果通过person_id查不到，尝试通过person_evidence_relation关联表查询
            if df.empty:
                if statement_type:
                    query2 = """
                        SELECT s.*, e.title, e.upload_time
                        FROM statements s
                        JOIN evidence_meta e ON s.evidence_id = e.evidence_id
                        JOIN person_evidence_relation per ON s.evidence_id = per.evidence_id
                        WHERE per.person_id = ? AND s.statement_type = ?
                    """
                    df = pd.read_sql(query2, conn, params=[user_id, statement_type])
                else:
                    query2 = """
                        SELECT s.*, e.title, e.upload_time
                        FROM statements s
                        JOIN evidence_meta e ON s.evidence_id = e.evidence_id
                        JOIN person_evidence_relation per ON s.evidence_id = per.evidence_id
                        WHERE per.person_id = ?
                    """
                    df = pd.read_sql(query2, conn, params=[user_id])

            conn.close()

            if df.empty:
                return json.dumps({"message": f"未找到用户 {user_id} 的供述证言记录"}, ensure_ascii=False)

            # 笔录内容可能很长，返回摘要信息
            result = []
            for _, row in df.iterrows():
                content = row['content']
                result.append({
                    'evidence_id': row['evidence_id'],
                    'title': row['title'],
                    'statement_type': row['statement_type'],
                    'upload_time': str(row['upload_time']),
                    'content_preview': content[:500] + '...' if len(content) > 500 else content,
                    'content_length': len(content)
                })
            return json.dumps({
                "说明": f"共找到{len(result)}份笔录，如需查看完整内容请使用 query_evidence_content 工具",
                "data": result
            }, ensure_ascii=False)

        elif tool_name == "query_documents":
            case_id = tool_input["case_id"]
            doc_subtype = tool_input.get("doc_subtype", "")

            conn = get_conn()
            if doc_subtype:
                # 支持模糊匹配（测谎报告→测谎，鉴定意见→鉴定）
                query = """
                    SELECT d.*, e.title, e.upload_time
                    FROM documents d
                    JOIN evidence_meta e ON d.evidence_id = e.evidence_id
                    WHERE e.case_id = ? AND d.doc_subtype LIKE ?
                """
                df = pd.read_sql(query, conn, params=[case_id, f"%{doc_subtype}%"])
            else:
                query = """
                    SELECT d.*, e.title, e.upload_time
                    FROM documents d
                    JOIN evidence_meta e ON d.evidence_id = e.evidence_id
                    WHERE e.case_id = ?
                """
                df = pd.read_sql(query, conn, params=[case_id])
            conn.close()

            if df.empty:
                return json.dumps({"message": "未找到文书记录"}, ensure_ascii=False)

            # 文书内容可能很长，返回摘要
            result = []
            for _, row in df.iterrows():
                content = row['content']
                result.append({
                    'title': row['title'],
                    'doc_subtype': row['doc_subtype'],
                    'upload_time': str(row['upload_time']),
                    'content_preview': content[:500] + '...' if len(content) > 500 else content,
                    'content_length': len(content)
                })
            return json.dumps({
                "说明": f"共找到{len(result)}份文书",
                "data": result
            }, ensure_ascii=False)

        elif tool_name == "query_evidence_content":
            evidence_id = tool_input["evidence_id"]

            conn = get_conn()

            # 先查询证据类型
            meta_query = "SELECT evidence_type, title FROM evidence_meta WHERE evidence_id = ?"
            meta = pd.read_sql(meta_query, conn, params=[evidence_id])

            if meta.empty:
                conn.close()
                return json.dumps({"message": f"未找到证据 {evidence_id}"}, ensure_ascii=False)

            evidence_type = meta.iloc[0]['evidence_type']
            title = meta.iloc[0]['title']

            # 根据证据类型查询具体内容表
            content = None
            if evidence_type in ['供述', '辩解', '证言']:
                query = "SELECT content FROM statements WHERE evidence_id = ?"
                df = pd.read_sql(query, conn, params=[evidence_id])
                if not df.empty:
                    content = df.iloc[0]['content']

            elif evidence_type in ['文书', '鉴定', '笔录', '测谎']:
                query = "SELECT content FROM documents WHERE evidence_id = ?"
                df = pd.read_sql(query, conn, params=[evidence_id])
                if not df.empty:
                    content = df.iloc[0]['content']

            conn.close()

            if content:
                return json.dumps({
                    "title": title,
                    "evidence_type": evidence_type,
                    "content": content
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "message": f"证据 {title} 的内容未被解析到数据库中，可能需要从原始文件读取"
                }, ensure_ascii=False)

        elif tool_name == "generate_investigation_profile":
            case_id = tool_input["case_id"]
            user_id = _resolve_user_id(tool_input["user_id"])

            # 调用专门的画像生成函数
            from src.investigation_profiler import generate_investigation_report
            report = generate_investigation_report(case_id, user_id)
            return report

        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# System Prompt 
# ============================================================

SYSTEM_PROMPT = """你是一名检察侦查AI助手,专门协助检察官分析刑事案件的多源证据数据。

## 你的角色
你是一个严谨、专业的检察侦查分析员。你的任务是基于多源证据数据库(资金流水、聊天记录、通话记录、轨迹数据、供述笔录、文书证据等),帮助检察官发现异常行为模式、追踪资金流向、识别可疑关系网络、分析证据链条。

## 工作原则
1. **绝对禁止编造数据**: 你只能引用工具返回的真实数据。绝对不能编造、猜测或推断任何记录、金额、时间、对话内容、轨迹位置等。如果工具没有返回某条数据,就不能在回复中提及它。这是最重要的原则。
2. **证据为先**: 每一个结论都必须有工具返回的具体数据支撑。如果工具返回的数据中找不到支撑,就不要做出该结论。
3. **不做推定**: 只描述数据中呈现的异常模式,不直接认定犯罪。使用"疑似"、"建议核查"等措辞。
4. **法言法语**: 使用规范的法律术语和检察业务用语。
5. **多源印证**: 优先寻找多源证据之间的印证关系,如资金往来与聊天记录的时间吻合、轨迹重合与通话频繁等。
6. **高效调用工具**:
   - 优先使用综合性工具(如 generate_full_profile)而非多次单独调用
   - 一次性调用多个相关工具,而不是逐个调用
   - 如果用户问题明确具体,只调用相关工具,不要做全面分析
   - 避免重复调用相同工具

## 关注的异常模式

### 资金流水异常
- 化整为零: 短时间内多笔小额转账合计为整数
- 深夜交易: 凌晨0-6点的资金往来
- 财富突增: 某月入账远超月均水平
- 高频个人转账: 与特定自然人的异常频繁往来
- 过桥账户: 资金经中间人转手后最终流向目标
- 资金回流: A→B→C→A 的环形资金流动

### 通讯行为异常
- 敏感词汇: 聊天记录中的隐喻暗语("老板"、"打点"、"意思意思"等)
- 异常通话: 案发时段的密集通话、深夜通话
- 快速删除: 通话后立即进行的资金操作

### 轨迹行为异常
- 时空碰撞: 多人在案发时段同时出现在同一地点
- 异常出行: 频繁往返于非正常工作地点
- 轨迹与供述不符: 声称不在现场但轨迹显示在场

### 供述矛盾
- 多次笔录中的前后矛盾
- 不同涉案人供述的相互矛盾
- 供述与客观证据(资金、轨迹)不符

## 使用工具的注意事项
- 所有需要 user_id 的工具都支持直接传入姓名(如"李四"),系统会自动解析为对应的 user_id。
- 当用户提到人名时,直接将姓名传入工具即可,无需先查询人员表。
- 如果不确定有哪些调查对象,先调用 query_persons 查看。
- 如果不确定有哪些案件,先调用 query_cases 查看。
- **查询证据全文的步骤**:
  1. 先用 query_person_evidences 或 query_case_evidences 获取证据列表(包含evidence_id和摘要)
  2. 如果需要查看某份证据的完整内容,使用 query_evidence_content 并传入对应的 evidence_id
- **查询特定类型证据**:
  - 供述/证言: 使用 query_statements
  - 测谎报告: 使用 query_documents，doc_subtype="鉴定"（测谎报告属于鉴定意见类型）
  - 起诉书/判决书: 使用 query_documents，doc_subtype="文书"
  - 聊天记录: 使用 query_chat_records
  - 通话记录: 使用 query_call_records

## 回答原则
1. **紧扣用户问题**: 用户问什么就重点分析什么。如果问"资金往来"就聚焦交易分析,如果问"聊天记录"就聚焦通讯内容,如果问"综合分析"就多源印证。不要每次都做全面分析。
2. **先精确查询再回答**: 根据用户问题选择合适的工具。如果问特定类型证据,先用对应的查询工具获取数据,再回答。
3. **只用工具返回的数据**: 回复中引用的每一个数据点(金额、时间、对话内容、位置)都必须能在工具返回的结果中找到原文。不能对数据做任何"补充"或"推断"。
4. **简洁有力**: 不要堆砌所有信息,突出与用户问题最相关的发现。
5. **控制工具调用次数**:
   - 如果需要全面分析某人,直接调用 generate_full_profile,它已包含基本信息、交易概况、异常检测、关系网络
   - 如果用户只问简单问题(如"李建是谁"),只需调用 query_persons,不要调用其他工具
   - 分析完一轮后要给出结论,不要无限制地继续调用工具

## 输出格式
使用 Markdown 格式让回复清晰易读:
- 用 ## 标题分节
- 用 **粗体** 强调关键信息和风险点
- 用表格展示对比数据
- 用列表展示要点
- 用引用块展示原始证据内容

## 语言要求
**必须始终使用中文回复。** 所有分析、结论、建议都用中文表达。包括工具调用的结果解读也用中文。
"""


# ============================================================
# Anthropic 协议
# ============================================================

def _chat_anthropic(messages: list, api_key: str, model: str, base_url: str = None) -> tuple:
    """Anthropic 原生协议调用"""
    import anthropic

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = anthropic.Anthropic(**kwargs)
    current_messages = list(messages)

    for iteration in range(20):  # 平衡性能和复杂查询需求
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS_ANTHROPIC,
            messages=current_messages,
        )

        # 记录迭代信息用于调试
       

        if response.stop_reason == "end_turn":
            text_parts = [block.text for block in response.content if block.type == "text"]
            assistant_reply = "\n".join(text_parts)
            current_messages.append({"role": "assistant", "content": response.content})
            return assistant_reply, current_messages

        if response.stop_reason == "tool_use":
            current_messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            current_messages.append({"role": "user", "content": tool_results})
            continue

        text_parts = [block.text for block in response.content if block.type == "text"]
        assistant_reply = "\n".join(text_parts) if text_parts else "分析完成。"
        current_messages.append({"role": "assistant", "content": response.content})
        return assistant_reply, current_messages

    return "分析迭代次数过多, 请简化问题后重试。", current_messages


def _chat_anthropic_stream(messages: list, api_key: str, model: str, base_url: str = None):
    """Anthropic 流式调用"""
    import anthropic

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = anthropic.Anthropic(**kwargs)
    current_messages = list(messages)

    for iteration in range(20):  # 平衡性能和复杂查询需求
        # 流式调用
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS_ANTHROPIC,
            messages=current_messages,
        ) as stream:
            text_buffer = ""
            content_blocks = []

            for event in stream:
                if hasattr(event, 'type'):
                    # 文本内容增量
                    if event.type == "content_block_delta":
                        if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
                            text_buffer += event.delta.text
                            yield {
                                "type": "text",
                                "content": event.delta.text,
                                "messages": current_messages
                            }

                    # 内容块完成
                    elif event.type == "content_block_stop":
                        if hasattr(event, 'content_block'):
                            content_blocks.append(event.content_block)

            # 获取完整的response
            response = stream.get_final_message()

            # 处理工具调用
            if response.stop_reason == "tool_use":
                current_messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        yield {
                            "type": "tool",
                            "content": f"\n\n🔧 调用工具: {block.name}\n",
                            "messages": current_messages
                        }
                        result = _execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                current_messages.append({"role": "user", "content": tool_results})
                continue  # 继续下一轮对话

            # 对话结束
            current_messages.append({"role": "assistant", "content": response.content})
            yield {
                "type": "done",
                "content": "",
                "messages": current_messages
            }
            return

    yield {"type": "error", "content": "\n\n分析迭代次数过多。"}


# ============================================================
# OpenAI 兼容协议 (适用于 OpenAI / DeepSeek / Qwen / 智谱 / Moonshot 等)
# ============================================================

def _chat_openai(messages: list, api_key: str, model: str, base_url: str) -> tuple:
    """OpenAI 兼容协议调用 (覆盖绝大部分国内厂商)"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 将消息格式统一为 OpenAI 格式 (纯文本 role/content)
    # 注意: OpenAI 协议下历史记录只保留纯文本, 工具调用在循环内处理
    oai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in messages:
        if isinstance(msg.get("content"), str):
            oai_messages.append({"role": msg["role"], "content": msg["content"]})

    current_messages = list(oai_messages)

    for iteration in range(20):  # 平衡性能和复杂查询需求
        response = client.chat.completions.create(
            model=model,
            messages=current_messages,
            tools=TOOLS_OPENAI,
            max_tokens=4096,
        )

        # 记录迭代信息用于调试
        if iteration > 10:
            print(f"[警告] Agent已迭代{iteration+1}次，可能存在循环调用")

        choice = response.choices[0]
        msg = choice.message

        # 没有工具调用 -> 返回最终回复
        if not msg.tool_calls:
            reply = msg.content or "分析完成。"
            # 返回简化的历史(OpenAI格式不保留tool内部细节到下一轮)
            return reply, messages + [
                {"role": "assistant", "content": reply}
            ]

        # 有工具调用 -> 执行并继续
        current_messages.append(msg.model_dump())

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            result = _execute_tool(fn_name, fn_args)
            current_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "分析迭代次数过多, 请简化问题后重试。", messages


def _chat_openai_stream(messages: list, api_key: str, model: str, base_url: str):
    """OpenAI 兼容协议流式调用"""
    from openai import OpenAI
    import sys
    import io
    import logging

    # 禁用 httpx 和 openai 的调试日志，避免编码问题
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # 确保在函数内也设置正确的编码
    if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except:
            pass

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 转换消息格式
    oai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in messages:
        if isinstance(msg.get("content"), str):
            oai_messages.append({"role": msg["role"], "content": msg["content"]})

    current_messages = list(oai_messages)

    for iteration in range(20):  # 平衡性能和复杂查询需求
        try:
            # 流式调用
            stream = client.chat.completions.create(
                model=model,
                messages=current_messages,
                tools=TOOLS_OPENAI,
                max_tokens=4096,
                stream=True,
            )

            text_buffer = ""
            tool_calls_buffer = []
            current_tool_call = None

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 文本内容
                if delta.content:
                    text_buffer += delta.content
                    yield {
                        "type": "text",
                        "content": delta.content,
                        "messages": messages
                    }

                # 工具调用
                if delta.tool_calls:
                    for tool_call_delta in delta.tool_calls:
                        if tool_call_delta.index is not None:
                            # 新的tool call
                            if current_tool_call is None or current_tool_call['index'] != tool_call_delta.index:
                                if current_tool_call:
                                    tool_calls_buffer.append(current_tool_call)
                                current_tool_call = {
                                    'index': tool_call_delta.index,
                                    'id': tool_call_delta.id or '',
                                    'type': 'function',
                                    'function': {
                                        'name': tool_call_delta.function.name or '',
                                        'arguments': tool_call_delta.function.arguments or ''
                                    }
                                }
                            else:
                                # 累积arguments
                                if tool_call_delta.function.arguments:
                                    current_tool_call['function']['arguments'] += tool_call_delta.function.arguments

            # 添加最后一个tool call
            if current_tool_call:
                tool_calls_buffer.append(current_tool_call)

            # 处理工具调用
            if tool_calls_buffer:
                # 构造完整的message对象
                msg_dict = {
                    "role": "assistant",
                    "content": text_buffer or None,
                    "tool_calls": tool_calls_buffer
                }
                current_messages.append(msg_dict)

                for tool_call in tool_calls_buffer:
                    fn_name = tool_call['function']['name']
                    fn_args = json.loads(tool_call['function']['arguments'])

                    yield {
                        "type": "tool",
                        "content": f"\n\n🔧 调用工具: {fn_name}\n",
                        "messages": messages
                    }

                    result = _execute_tool(fn_name, fn_args)
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": result,
                    })

                continue  # 继续下一轮

            # 没有工具调用，对话结束
            yield {
                "type": "done",
                "content": "",
                "messages": messages + [{"role": "assistant", "content": text_buffer}]
            }
            return

        except Exception as e:
            # 安全地获取错误信息，避免编码问题
            try:
                error_msg = str(e)
            except:
                error_msg = repr(e)

            yield {
                "type": "error",
                "content": f"流式调用出错(第{iteration+1}轮): {error_msg}"
            }
            return

    yield {"type": "error", "content": "\n\n分析迭代次数过多。"}


# ============================================================
# 统一入口
# ============================================================

def chat_with_agent(
    messages: list,
    provider_id: str = "anthropic",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
) -> tuple:
    """
    与 Agent 对话 (统一入口, 自动路由到对应协议)。

    Args:
        messages: 对话历史
        provider_id: 厂商ID (anthropic/openai/deepseek/qwen/zhipu/moonshot/custom)
        api_key: API Key (优先使用传入值, 否则读环境变量)
        model: 模型名 (留空用厂商默认模型)
        base_url: 自定义 base_url (仅 custom 厂商需要)

    Returns:
        (assistant_reply, updated_messages)
    """
    provider = LLM_PROVIDERS.get(provider_id, LLM_PROVIDERS["anthropic"])
    protocol = provider["protocol"]

    # 确定 API Key
    key = api_key or get_provider_api_key(provider_id)
    if not key:
        return f"请输入 {provider['name']} 的 API Key", messages

    # 确定模型
    use_model = model or provider["default_model"]
    if not use_model:
        return "请指定模型名称", messages

    # 确定 base_url
    use_base_url = base_url or provider.get("base_url") or None

    try:
        if protocol == "anthropic":
            return _chat_anthropic(messages, key, use_model, use_base_url)
        else:
            if not use_base_url:
                return "OpenAI 兼容协议需要 base_url, 请检查配置", messages
            return _chat_openai(messages, key, use_model, use_base_url)
    except Exception as e:
        return f"调用 {provider['name']} ({use_model}) 失败: {e}", messages


def chat_with_agent_stream(
    messages: list,
    provider_id: str = "anthropic",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
):
    """
    与 Agent 对话 - 流式版本 (返回生成器)

    Args:
        messages: 对话历史
        provider_id: 厂商ID
        api_key: API Key
        model: 模型名
        base_url: 自定义 base_url

    Yields:
        dict: {"type": "text|tool|done|error", "content": str, "messages": list}
    """
    provider = LLM_PROVIDERS.get(provider_id, LLM_PROVIDERS["anthropic"])
    protocol = provider["protocol"]

    # 确定参数
    key = api_key or get_provider_api_key(provider_id)
    if not key:
        yield {"type": "error", "content": f"请输入 {provider['name']} 的 API Key"}
        return

    use_model = model or provider["default_model"]
    if not use_model:
        yield {"type": "error", "content": "请指定模型名称"}
        return

    use_base_url = base_url or provider.get("base_url") or None

    try:
        if protocol == "anthropic":
            yield from _chat_anthropic_stream(messages, key, use_model, use_base_url)
        else:
            if not use_base_url:
                yield {"type": "error", "content": "OpenAI 兼容协议需要 base_url"}
                return
            yield from _chat_openai_stream(messages, key, use_model, use_base_url)
    except Exception as e:
        yield {"type": "error", "content": f"调用失败: {str(e)}"}
