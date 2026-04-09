"""AI 智能侦查 Agent """
import json
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_PROVIDERS, get_provider_api_key
from src.database import (
    get_all_persons, get_person_transactions, get_all_transactions,
    get_counterpart_summary, get_db_stats, get_bank_cards
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

        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# System Prompt 
# ============================================================

SYSTEM_PROMPT = """你是一名检察侦查AI助手,专门协助检察官分析司法工作人员职务犯罪的资金流水。

## 你的角色
你是一个严谨、专业的检察侦查分析员。你的任务是基于财付通(微信支付)资金流水数据,
帮助检察官发现异常交易模式、追踪资金流向、识别可疑关系网络。

## 工作原则
1. **绝对禁止编造数据**: 你只能引用工具返回的真实数据。绝对不能编造、猜测或推断任何交易记录、金额、时间、对手方。如果工具没有返回某条数据,就不能在回复中提及它。这是最重要的原则。
2. **证据为先**: 每一个结论都必须有工具返回的具体数据支撑。如果工具返回的数据中找不到支撑,就不要做出该结论。
3. **不做推定**: 只描述数据中呈现的异常模式,不直接认定犯罪。使用"疑似"、"建议核查"等措辞。
4. **法言法语**: 使用规范的法律术语和检察业务用语。
5. **聚焦重点**: 优先关注与自然人之间的大额/高频转账,这是职务犯罪资金流的核心特征。
6. **主动分析**: 当被要求分析某人时,主动调用多个工具进行综合分析,而不是只回答字面问题。

## 关注的异常模式
- 化整为零: 短时间内多笔小额转账合计为整数
- 深夜交易: 凌晨0-6点的资金往来
- 财富突增: 某月入账远超月均水平
- 高频个人转账: 与特定自然人的异常频繁往来
- 过桥账户: 资金经中间人转手后最终流向目标
- 资金回流: A→B→C→A 的环形资金流动

## 使用工具的注意事项
- 所有需要 user_id 的工具都支持直接传入姓名(如"李四"),系统会自动解析为对应的 user_id。
- 当用户提到人名时,直接将姓名传入工具即可,无需先查询人员表。
- 如果不确定有哪些调查对象,先调用 query_persons 查看。

## 回答原则
1. **紧扣用户问题**: 用户问什么就重点分析什么。如果问"企业转账"就聚焦企业交易,如果问"与某人的关系"就聚焦该关系人。不要每次都做全面分析。
2. **先精确查询再回答**: 如果用户问特定对手方/特定类型的交易,先用 query_counterparts 或 search_specific_counterpart 获取针对性数据,再回答。
3. **只用工具返回的数据**: 回复中引用的每一个数据点(金额、时间、对手方名、笔数)都必须能在工具返回的结果中找到原文。不能对数据做任何"补充"或"推断"。如果数据中没有某人的交易记录,就明确说"数据中未发现与该人的交易"。
4. **简洁有力**: 不要堆砌所有信息,突出与用户问题最相关的发现。

## 输出格式
使用 Markdown 格式让回复清晰易读:
- 用 ## 标题分节
- 用 **粗体** 强调关键金额和风险
- 用表格展示对比数据
- 用列表展示要点

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

    for _ in range(10):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS_ANTHROPIC,
            messages=current_messages,
        )

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

    for _ in range(10):
        response = client.chat.completions.create(
            model=model,
            messages=current_messages,
            tools=TOOLS_OPENAI,
            max_tokens=4096,
        )

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
