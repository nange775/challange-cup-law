"""基于 NetworkX 的关系图谱分析模块"""
import json
import networkx as nx
import pandas as pd
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import get_all_persons, get_all_transactions, get_conn


def build_transaction_graph(df: pd.DataFrame) -> nx.DiGraph:
    """
    从交易数据构建有向资金流转图。
    节点: 人员/账户
    边: 资金流向, 权重为交易总金额
    """
    G = nx.DiGraph()

    if df.empty:
        return G

    for _, row in df.iterrows():
        user = row.get("user_name", row.get("user_id", ""))
        counterpart = row.get("counterpart_name", "")
        if not counterpart or counterpart == "":
            continue

        amount = row["amount"] / 100  # 转为元

        if row["direction"] == "出":
            src, dst = user, counterpart
        else:
            src, dst = counterpart, user

        # 添加/更新节点
        if not G.has_node(src):
            G.add_node(src, type="unknown", total_out=0, total_in=0, tx_count=0)
        if not G.has_node(dst):
            G.add_node(dst, type="unknown", total_out=0, total_in=0, tx_count=0)

        G.nodes[src]["total_out"] += amount
        G.nodes[src]["tx_count"] += 1
        G.nodes[dst]["total_in"] += amount
        G.nodes[dst]["tx_count"] += 1

        # 添加/更新边
        if G.has_edge(src, dst):
            G[src][dst]["weight"] += amount
            G[src][dst]["count"] += 1
        else:
            G.add_edge(src, dst, weight=amount, count=1)

    # 标记节点类型
    for node in G.nodes():
        name = str(node)
        if any(kw in name for kw in ["公司", "有限", "银联", "财付通", "科技", "管理", "股份"]):
            G.nodes[node]["type"] = "enterprise"
        elif len(name) <= 4:
            G.nodes[node]["type"] = "person"
        else:
            G.nodes[node]["type"] = "enterprise"

    return G


def find_bridge_accounts(G: nx.DiGraph, target: str) -> list:
    """
    寻找过桥账户(白手套)：
    在目标人物的交易网络中, 既接收目标资金又向外转出的中间人。
    模式: 嫌疑人 -> 中间人 -> 第三方 (或反向)
    """
    if target not in G:
        return []

    bridges = []
    # 目标的直接出账对手
    out_neighbors = set(G.successors(target))
    # 目标的直接入账来源
    in_neighbors = set(G.predecessors(target))

    for mid in out_neighbors:
        if mid == target or G.nodes[mid]["type"] == "enterprise":
            continue
        # 中间人又向其他人转账
        mid_outs = set(G.successors(mid)) - {target}
        if mid_outs:
            flow_to_mid = G[target][mid]["weight"]
            flow_from_mid = sum(G[mid][out]["weight"] for out in mid_outs if G.has_edge(mid, out))
            bridges.append({
                "bridge_name": mid,
                "direction": "出",
                "flow_in": flow_to_mid,
                "flow_out": flow_from_mid,
                "downstream": list(mid_outs)[:5],
                "suspicion": min(flow_to_mid, flow_from_mid) / max(flow_to_mid, flow_from_mid)
                             if max(flow_to_mid, flow_from_mid) > 0 else 0,
            })

    for mid in in_neighbors:
        if mid == target or G.nodes[mid]["type"] == "enterprise":
            continue
        # 中间人又从其他人收钱
        mid_ins = set(G.predecessors(mid)) - {target}
        if mid_ins:
            flow_from_mid = G[mid][target]["weight"]
            flow_to_mid = sum(G[src][mid]["weight"] for src in mid_ins if G.has_edge(src, mid))
            bridges.append({
                "bridge_name": mid,
                "direction": "入",
                "flow_in": flow_to_mid,
                "flow_out": flow_from_mid,
                "upstream": list(mid_ins)[:5],
                "suspicion": min(flow_to_mid, flow_from_mid) / max(flow_to_mid, flow_from_mid)
                             if max(flow_to_mid, flow_from_mid) > 0 else 0,
            })

    return sorted(bridges, key=lambda x: x["suspicion"], reverse=True)


def find_fund_cycles(G: nx.DiGraph, target: str, max_length: int = 4) -> list:
    """
    资金回流检测：寻找涉及目标人物的资金环路。
    A -> B -> C -> A 模式表明可能存在洗钱或掩饰资金来源。
    """
    if target not in G:
        return []

    cycles = []
    try:
        for cycle in nx.simple_cycles(G, length_bound=max_length):
            if target in cycle:
                # 计算环路上最小流量(瓶颈)
                min_flow = float('inf')
                for i in range(len(cycle)):
                    src = cycle[i]
                    dst = cycle[(i + 1) % len(cycle)]
                    if G.has_edge(src, dst):
                        min_flow = min(min_flow, G[src][dst]["weight"])
                    else:
                        min_flow = 0
                        break
                if min_flow > 0:
                    cycles.append({
                        "path": cycle,
                        "min_flow_yuan": min_flow,
                        "length": len(cycle),
                    })
    except Exception:
        pass

    return sorted(cycles, key=lambda x: x["min_flow_yuan"], reverse=True)[:20]


def get_network_metrics(G: nx.DiGraph, target: str) -> dict:
    """计算目标人物的网络特征指标"""
    if target not in G:
        return {}

    # 只看person类型的邻居
    person_neighbors = [
        n for n in set(list(G.successors(target)) + list(G.predecessors(target)))
        if G.nodes[n]["type"] == "person"
    ]

    return {
        "degree": G.degree(target),
        "in_degree": G.in_degree(target),
        "out_degree": G.out_degree(target),
        "person_contacts": len(person_neighbors),
        "total_in_yuan": G.nodes[target].get("total_in", 0),
        "total_out_yuan": G.nodes[target].get("total_out", 0),
    }


def get_top_counterparts(G: nx.DiGraph, target: str, top_n: int = 10) -> list:
    """获取目标人物资金往来最密切的对手方"""
    if target not in G:
        return []

    counterparts = {}

    for succ in G.successors(target):
        edge = G[target][succ]
        counterparts[succ] = counterparts.get(succ, {"name": succ, "out": 0, "in": 0, "count": 0})
        counterparts[succ]["out"] += edge["weight"]
        counterparts[succ]["count"] += edge["count"]

    for pred in G.predecessors(target):
        edge = G[pred][target]
        counterparts[pred] = counterparts.get(pred, {"name": pred, "out": 0, "in": 0, "count": 0})
        counterparts[pred]["in"] += edge["weight"]
        counterparts[pred]["count"] += edge["count"]

    result = sorted(counterparts.values(), key=lambda x: x["out"] + x["in"], reverse=True)
    return result[:top_n]


def generate_pyvis_html(G: nx.DiGraph, target: str, output_path: str = None) -> str:
    """生成交互式图谱 HTML（使用国内CDN）"""
    import json

    # 只保留与target有直接关系的节点(1跳邻居), 以及邻居间的关系
    neighbors = set(list(G.successors(target)) + list(G.predecessors(target)))
    subgraph_nodes = {target} | neighbors

    nodes = []
    edges = []

    for node in subgraph_nodes:
        if node not in G:
            continue
        node_data = G.nodes[node]
        if node == target:
            color = "#e74c3c"
            size = 40
        elif node_data.get("type") == "person":
            color = "#3498db"
            size = 25
        else:
            color = "#95a5a6"
            size = 20

        label = str(node)[:8]
        title = (
            f"姓名: {node}\n"
            f"类型: {node_data.get('type', 'unknown')}\n"
            f"入账: {node_data.get('total_in', 0):.0f}元\n"
            f"出账: {node_data.get('total_out', 0):.0f}元\n"
            f"交易笔数: {node_data.get('tx_count', 0)}"
        )
        nodes.append({
            "id": str(node),
            "label": label,
            "title": title,
            "color": color,
            "size": size,
        })

    for src, dst in G.edges():
        if src in subgraph_nodes and dst in subgraph_nodes:
            edge_data = G[src][dst]
            weight = edge_data["weight"]
            count = edge_data["count"]
            width = max(1, min(10, weight / 5000))
            color = "#e74c3c" if weight >= 10000 else "#7f8c8d"
            title = f"金额: {weight:.0f}元, 笔数: {count}"
            edges.append({
                "from": str(src),
                "to": str(dst),
                "width": width,
                "color": color,
                "title": title,
                "label": f"{weight:.0f}",
                "arrows": "to"
            })

    # 生成自定义HTML（使用国内CDN）
    html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>关系图谱</title>
    <script src="https://cdn.bootcdn.net/ajax/libs/vis-network/9.1.2/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: Arial, sans-serif; }}
        #network {{ width: 100%; height: 600px; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <div id="network"></div>
    <script>
        var nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
        var edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            physics: {{
                barnesHut: {{
                    gravitationalConstant: -3000,
                    centralGravity: 0.3,
                    springLength: 200
                }}
            }},
            edges: {{
                arrows: {{ to: {{ enabled: true }} }},
                smooth: {{ type: 'continuous' }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100
            }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>
"""

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_template)
        return output_path
    else:
        return html_template


def _load_person_maps() -> tuple:
    """加载人员映射，便于在 user_id 和姓名之间互相转换。"""
    persons = get_all_persons()
    id_to_name = {}
    name_to_id = {}
    if not persons.empty:
        for _, row in persons.iterrows():
            user_id = str(row.get("user_id", "") or "").strip()
            name = str(row.get("name", "") or "").strip()
            if user_id:
                id_to_name[user_id] = name or user_id
            if name and user_id:
                name_to_id[name] = user_id
    return persons, id_to_name, name_to_id


def _person_display(user_id: str, id_to_name: dict) -> str:
    """统一人员展示名称。"""
    return id_to_name.get(user_id, user_id)


def _resolve_counterpart_identity(row: pd.Series, current_id: str, id_to_name: dict, name_to_id: dict) -> tuple:
    """从交易记录中提取对手方身份。"""
    user_id = str(row.get("user_id", "") or "").strip()
    user_name = str(row.get("user_name", "") or "").strip()
    counterpart_id = str(row.get("counterpart_id", "") or "").strip()
    counterpart_name = str(row.get("counterpart_name", "") or "").strip()

    if user_id == current_id:
        if counterpart_id:
            return counterpart_id, counterpart_name or _person_display(counterpart_id, id_to_name)
        if counterpart_name:
            return name_to_id.get(counterpart_name, counterpart_name), counterpart_name
    else:
        if user_id:
            return user_id, user_name or _person_display(user_id, id_to_name)
        if user_name:
            return name_to_id.get(user_name, user_name), user_name
    return "", ""


def _query_direct_transactions(user_a: str, user_b: str, name_a: str, name_b: str) -> pd.DataFrame:
    """查询两人之间的直接交易。"""
    conn = get_conn()
    query = """
        SELECT *
        FROM transactions
        WHERE
            (
                user_id = ?
                AND (counterpart_id = ? OR counterpart_name = ?)
            )
            OR
            (
                user_id = ?
                AND (counterpart_id = ? OR counterpart_name = ?)
            )
        ORDER BY trade_time
    """
    df = pd.read_sql(query, conn, params=[user_a, user_b, name_b, user_b, user_a, name_a])
    conn.close()
    if not df.empty:
        df["trade_time"] = pd.to_datetime(df["trade_time"], errors="coerce")
        df["amount_yuan"] = df["amount"].fillna(0) / 100
    return df


def _query_chat_relation(user_a: str, user_b: str) -> pd.DataFrame:
    """查询两人之间的聊天记录。"""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT *
        FROM chat_records
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY send_time
        """,
        conn,
        params=[user_a, user_b, user_b, user_a]
    )
    conn.close()
    return df


def _query_call_relation(user_a: str, user_b: str) -> pd.DataFrame:
    """查询两人之间的通话记录。"""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT *
        FROM call_records
        WHERE
            (caller_id = ? AND callee_id = ?)
            OR
            (caller_id = ? AND callee_id = ?)
        ORDER BY call_time
        """,
        conn,
        params=[user_a, user_b, user_b, user_a]
    )
    conn.close()
    return df


def _query_shared_evidence(user_a: str, user_b: str) -> pd.DataFrame:
    """查询两人共同关联的证据。"""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT
            e.evidence_id,
            e.case_id,
            e.evidence_type,
            e.title,
            e.upload_time
        FROM evidence_meta e
        JOIN person_evidence_relation r1 ON e.evidence_id = r1.evidence_id
        JOIN person_evidence_relation r2 ON e.evidence_id = r2.evidence_id
        WHERE r1.person_id = ? AND r2.person_id = ?
        ORDER BY e.upload_time DESC
        """,
        conn,
        params=[user_a, user_b]
    )
    conn.close()
    return df


def _collect_tx_contacts(target_id: str, target_name: str, id_to_name: dict, name_to_id: dict) -> dict:
    """收集某个人的交易联系人。"""
    all_tx = get_all_transactions()
    contacts = {}
    if all_tx.empty:
        return contacts

    related = all_tx[
        (all_tx["user_id"].astype(str) == target_id)
        | (all_tx["counterpart_id"].fillna("").astype(str) == target_id)
        | (all_tx["counterpart_name"].fillna("").astype(str) == target_name)
    ]

    for _, row in related.iterrows():
        other_id, other_name = _resolve_counterpart_identity(row, target_id, id_to_name, name_to_id)
        if not other_id or other_id == target_id:
            continue
        item = contacts.setdefault(other_id, {
            "person_id": other_id,
            "name": other_name or _person_display(other_id, id_to_name),
            "tx_count": 0,
            "tx_amount_yuan": 0.0,
        })
        item["tx_count"] += 1
        item["tx_amount_yuan"] += float(row.get("amount_yuan", 0) or 0)
    return contacts


def _collect_chat_contacts(target_id: str, id_to_name: dict) -> dict:
    """收集某个人的聊天联系人。"""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT sender_id, receiver_id, send_time, content
        FROM chat_records
        WHERE sender_id = ? OR receiver_id = ?
        """,
        conn,
        params=[target_id, target_id]
    )
    conn.close()
    contacts = {}
    if df.empty:
        return contacts
    for _, row in df.iterrows():
        other_id = row["receiver_id"] if row["sender_id"] == target_id else row["sender_id"]
        if not other_id or other_id == target_id:
            continue
        item = contacts.setdefault(other_id, {
            "person_id": other_id,
            "name": _person_display(other_id, id_to_name),
            "chat_count": 0,
        })
        item["chat_count"] += 1
    return contacts


def _collect_call_contacts(target_id: str, id_to_name: dict) -> dict:
    """收集某个人的通话联系人。"""
    conn = get_conn()
    df = pd.read_sql(
        """
        SELECT caller_id, callee_id, duration
        FROM call_records
        WHERE caller_id = ? OR callee_id = ?
        """,
        conn,
        params=[target_id, target_id]
    )
    conn.close()
    contacts = {}
    if df.empty:
        return contacts
    for _, row in df.iterrows():
        other_id = row["callee_id"] if row["caller_id"] == target_id else row["caller_id"]
        if not other_id or other_id == target_id:
            continue
        item = contacts.setdefault(other_id, {
            "person_id": other_id,
            "name": _person_display(other_id, id_to_name),
            "call_count": 0,
            "call_duration": 0,
        })
        item["call_count"] += 1
        item["call_duration"] += int(row.get("duration", 0) or 0)
    return contacts


def _merge_common_contacts(a_contacts: dict, b_contacts: dict) -> list:
    """合并共同联系人。"""
    common_ids = set(a_contacts.keys()) & set(b_contacts.keys())
    merged = []
    for person_id in common_ids:
        a_item = a_contacts[person_id]
        b_item = b_contacts[person_id]
        merged.append({
            "person_id": person_id,
            "name": a_item.get("name") or b_item.get("name") or person_id,
            "a_tx_count": a_item.get("tx_count", 0),
            "b_tx_count": b_item.get("tx_count", 0),
            "a_chat_count": a_item.get("chat_count", 0),
            "b_chat_count": b_item.get("chat_count", 0),
            "a_call_count": a_item.get("call_count", 0),
            "b_call_count": b_item.get("call_count", 0),
            "a_tx_amount_yuan": round(a_item.get("tx_amount_yuan", 0), 2),
            "b_tx_amount_yuan": round(b_item.get("tx_amount_yuan", 0), 2),
        })
    merged.sort(
        key=lambda item: (
            item["a_tx_count"] + item["b_tx_count"]
            + item["a_chat_count"] + item["b_chat_count"]
            + item["a_call_count"] + item["b_call_count"]
        ),
        reverse=True
    )
    return merged


def _build_relation_graph(id_to_name: dict, name_to_id: dict) -> nx.Graph:
    """构建用于最短路径分析的多关系无向图。"""
    G = nx.Graph()

    all_tx = get_all_transactions()
    if not all_tx.empty:
        for _, row in all_tx.iterrows():
            user_id = str(row.get("user_id", "") or "").strip()
            if not user_id:
                continue
            other_id, other_name = _resolve_counterpart_identity(row, user_id, id_to_name, name_to_id)
            if not other_id or other_id == user_id:
                continue
            if not G.has_edge(user_id, other_id):
                G.add_edge(user_id, other_id, relations=set(), weights=defaultdict(int))
            G[user_id][other_id]["relations"].add("transaction")
            G[user_id][other_id]["weights"]["transaction"] += 1

    conn = get_conn()
    chat_df = pd.read_sql("SELECT sender_id, receiver_id FROM chat_records", conn)
    call_df = pd.read_sql("SELECT caller_id, callee_id FROM call_records", conn)
    conn.close()

    if not chat_df.empty:
        for _, row in chat_df.iterrows():
            src = str(row.get("sender_id", "") or "").strip()
            dst = str(row.get("receiver_id", "") or "").strip()
            if not src or not dst or src == dst:
                continue
            if not G.has_edge(src, dst):
                G.add_edge(src, dst, relations=set(), weights=defaultdict(int))
            G[src][dst]["relations"].add("chat")
            G[src][dst]["weights"]["chat"] += 1

    if not call_df.empty:
        for _, row in call_df.iterrows():
            src = str(row.get("caller_id", "") or "").strip()
            dst = str(row.get("callee_id", "") or "").strip()
            if not src or not dst or src == dst:
                continue
            if not G.has_edge(src, dst):
                G.add_edge(src, dst, relations=set(), weights=defaultdict(int))
            G[src][dst]["relations"].add("call")
            G[src][dst]["weights"]["call"] += 1

    return G


def _summarize_direct_transactions(df: pd.DataFrame, user_a: str, user_b: str, name_a: str, name_b: str) -> dict:
    """汇总直接资金关系。"""
    summary = {
        "count": 0,
        "total_amount_yuan": 0.0,
        "a_to_b_count": 0,
        "b_to_a_count": 0,
        "a_to_b_amount_yuan": 0.0,
        "b_to_a_amount_yuan": 0.0,
        "first_time": None,
        "last_time": None,
        "samples": [],
    }
    if df.empty:
        return summary

    for _, row in df.iterrows():
        amount_yuan = float(row.get("amount_yuan", 0) or 0)
        summary["count"] += 1
        summary["total_amount_yuan"] += amount_yuan
        if str(row.get("user_id", "")) == user_a:
            summary["a_to_b_count"] += 1
            summary["a_to_b_amount_yuan"] += amount_yuan
        elif str(row.get("user_id", "")) == user_b:
            summary["b_to_a_count"] += 1
            summary["b_to_a_amount_yuan"] += amount_yuan

    valid_times = df["trade_time"].dropna()
    if not valid_times.empty:
        summary["first_time"] = valid_times.min().strftime("%Y-%m-%d %H:%M:%S")
        summary["last_time"] = valid_times.max().strftime("%Y-%m-%d %H:%M:%S")

    samples = df[["trade_time", "user_name", "counterpart_name", "amount_yuan", "purpose", "direction"]].copy()
    samples["trade_time"] = samples["trade_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    summary["samples"] = json.loads(samples.head(10).to_json(orient="records", force_ascii=False))
    summary["total_amount_yuan"] = round(summary["total_amount_yuan"], 2)
    summary["a_to_b_amount_yuan"] = round(summary["a_to_b_amount_yuan"], 2)
    summary["b_to_a_amount_yuan"] = round(summary["b_to_a_amount_yuan"], 2)
    summary["a_name"] = name_a
    summary["b_name"] = name_b
    return summary


def _summarize_chat_relation(df: pd.DataFrame) -> dict:
    """汇总聊天关系。"""
    summary = {
        "count": 0,
        "first_time": None,
        "last_time": None,
        "samples": [],
    }
    if df.empty:
        return summary
    summary["count"] = int(len(df))
    if "send_time" in df.columns:
        valid = df["send_time"].dropna().astype(str)
        if not valid.empty:
            summary["first_time"] = valid.iloc[0]
            summary["last_time"] = valid.iloc[-1]
    sample_cols = [col for col in ["send_time", "content", "message_type"] if col in df.columns]
    summary["samples"] = json.loads(df[sample_cols].head(10).to_json(orient="records", force_ascii=False))
    return summary


def _summarize_call_relation(df: pd.DataFrame) -> dict:
    """汇总通话关系。"""
    summary = {
        "count": 0,
        "total_duration": 0,
        "first_time": None,
        "last_time": None,
        "samples": [],
    }
    if df.empty:
        return summary
    summary["count"] = int(len(df))
    summary["total_duration"] = int(df["duration"].fillna(0).sum()) if "duration" in df.columns else 0
    if "call_time" in df.columns:
        valid = df["call_time"].dropna().astype(str)
        if not valid.empty:
            summary["first_time"] = valid.iloc[0]
            summary["last_time"] = valid.iloc[-1]
    sample_cols = [col for col in ["call_time", "duration"] if col in df.columns]
    summary["samples"] = json.loads(df[sample_cols].head(10).to_json(orient="records", force_ascii=False))
    return summary


def _summarize_shared_evidence(df: pd.DataFrame) -> dict:
    """汇总共同证据。"""
    summary = {
        "count": 0,
        "types": [],
        "samples": [],
    }
    if df.empty:
        return summary
    summary["count"] = int(len(df))
    if "evidence_type" in df.columns:
        type_counts = df["evidence_type"].fillna("未知").value_counts()
        summary["types"] = [
            {"evidence_type": str(k), "count": int(v)}
            for k, v in type_counts.items()
        ]
    sample_cols = [col for col in ["evidence_id", "case_id", "evidence_type", "title", "upload_time"] if col in df.columns]
    summary["samples"] = json.loads(df[sample_cols].head(10).to_json(orient="records", force_ascii=False))
    return summary


def _calculate_relation_score(direct_tx: dict, chat: dict, call: dict, common_contacts: list, shortest_path: dict, shared_evidence: dict) -> dict:
    """计算关系强度评分。"""
    score = 0
    reasons = []

    if direct_tx["count"] > 0:
        tx_score = min(40, direct_tx["count"] * 5 + int(direct_tx["total_amount_yuan"] / 2000))
        score += tx_score
        reasons.append(f"存在直接资金往来 {direct_tx['count']} 笔")

    if chat["count"] > 0:
        chat_score = min(20, chat["count"] * 2)
        score += chat_score
        reasons.append(f"存在聊天记录 {chat['count']} 条")

    if call["count"] > 0:
        call_score = min(20, call["count"] * 3 + int(call["total_duration"] / 120))
        score += call_score
        reasons.append(f"存在通话记录 {call['count']} 次")

    if common_contacts:
        common_score = min(10, len(common_contacts) * 2)
        score += common_score
        reasons.append(f"存在共同联系人 {len(common_contacts)} 个")

    if shortest_path.get("exists"):
        path_len = shortest_path.get("length", 0)
        if path_len == 2:
            score += 10
            reasons.append("两人之间存在直接图谱连接")
        elif path_len > 2:
            score += max(2, 10 - path_len)
            reasons.append(f"两人可通过 {path_len - 2} 个中间节点建立联系")

    if shared_evidence["count"] > 0:
        evidence_score = min(10, shared_evidence["count"] * 3)
        score += evidence_score
        reasons.append(f"存在共同证据 {shared_evidence['count']} 份")

    score = min(100, int(score))
    if score >= 70:
        level = "强关联"
    elif score >= 40:
        level = "中关联"
    elif score > 0:
        level = "弱关联"
    else:
        level = "无明显关联"

    return {"score": score, "level": level, "reasons": reasons}


def _build_summary_text(name_a: str, name_b: str, direct_tx: dict, chat: dict, call: dict, common_contacts: list, shortest_path: dict, shared_evidence: dict, score_info: dict) -> str:
    """生成关系摘要模板。"""
    parts = [f"{name_a} 与 {name_b} 的综合关系判定为“{score_info['level']}”（{score_info['score']}分）。"]

    if direct_tx["count"] > 0:
        parts.append(
            f"双方存在直接资金往来 {direct_tx['count']} 笔，"
            f"总金额约 {direct_tx['total_amount_yuan']:.2f} 元。"
        )

    if chat["count"] > 0:
        parts.append(f"双方存在聊天记录 {chat['count']} 条。")

    if call["count"] > 0:
        parts.append(f"双方存在通话记录 {call['count']} 次，总时长 {call['total_duration']} 秒。")

    if common_contacts:
        preview = "、".join(item["name"] for item in common_contacts[:3])
        parts.append(f"双方存在共同联系人 {len(common_contacts)} 个，主要包括 {preview}。")

    if shortest_path.get("exists") and shortest_path.get("length", 0) > 2:
        path_names = " -> ".join(shortest_path.get("path_names", []))
        parts.append(f"图谱最短路径为：{path_names}。")

    if shared_evidence["count"] > 0:
        parts.append(f"双方共同关联证据 {shared_evidence['count']} 份。")

    if len(parts) == 1:
        parts.append("当前数据中未发现明确的直接或间接关联。")

    return " ".join(parts)


def _generate_relationship_html(analysis: dict) -> str:
    """生成双节点关系可视化 HTML。"""
    person_a = analysis["person_a"]
    person_b = analysis["person_b"]
    direct_tx = analysis["direct_transactions"]
    chat = analysis["chat_relation"]
    call = analysis["call_relation"]
    shared_evidence = analysis["shared_evidence"]
    common_contacts = analysis["common_contacts"][:8]
    shortest_path = analysis["shortest_path"]

    nodes = [
        {"id": person_a["user_id"], "label": person_a["name"], "color": "#e74c3c", "size": 38, "shape": "dot"},
        {"id": person_b["user_id"], "label": person_b["name"], "color": "#409eff", "size": 38, "shape": "dot"},
    ]
    edges = []
    edge_id = 0

    def add_edge(src, dst, label, color, width=3, dashes=False, roundness=0.0, arrows=""):
        nonlocal edge_id
        edge_id += 1
        edges.append({
            "id": f"edge_{edge_id}",
            "from": src,
            "to": dst,
            "label": label,
            "color": {"color": color},
            "width": width,
            "font": {"align": "middle", "size": 12, "strokeWidth": 3},
            "dashes": dashes,
            "arrows": arrows,
            "smooth": {"enabled": True, "type": "curvedCW", "roundness": roundness},
        })

    if direct_tx["a_to_b_count"] > 0:
        add_edge(
            person_a["user_id"],
            person_b["user_id"],
            f"资金 {direct_tx['a_to_b_count']}笔 / {direct_tx['a_to_b_amount_yuan']:.0f}元",
            "#2ecc71",
            width=4,
            roundness=0.15,
            arrows="to",
        )
    if direct_tx["b_to_a_count"] > 0:
        add_edge(
            person_b["user_id"],
            person_a["user_id"],
            f"资金 {direct_tx['b_to_a_count']}笔 / {direct_tx['b_to_a_amount_yuan']:.0f}元",
            "#27ae60",
            width=4,
            roundness=0.3,
            arrows="to",
        )
    if chat["count"] > 0:
        add_edge(person_a["user_id"], person_b["user_id"], f"聊天 {chat['count']}条", "#3498db", width=3, dashes=True, roundness=0.45)
    if call["count"] > 0:
        add_edge(person_a["user_id"], person_b["user_id"], f"通话 {call['count']}次", "#f39c12", width=3, dashes=True, roundness=0.6)
    if shared_evidence["count"] > 0:
        add_edge(person_a["user_id"], person_b["user_id"], f"共证据 {shared_evidence['count']}份", "#9b59b6", width=3, dashes=[8, 6], roundness=0.75)

    for item in common_contacts:
        nodes.append({
            "id": item["person_id"],
            "label": item["name"],
            "color": "#95a5a6",
            "size": 24,
            "shape": "dot",
        })
        add_edge(person_a["user_id"], item["person_id"], f"A联系 {item['a_tx_count'] + item['a_chat_count'] + item['a_call_count']}", "#bdc3c7", width=2, dashes=True, roundness=0.15)
        add_edge(item["person_id"], person_b["user_id"], f"B联系 {item['b_tx_count'] + item['b_chat_count'] + item['b_call_count']}", "#bdc3c7", width=2, dashes=True, roundness=0.15)

    if shortest_path.get("exists") and shortest_path.get("length", 0) > 2:
        path = shortest_path.get("path", [])
        path_names = shortest_path.get("path_names", [])
        for node_id, node_name in zip(path[1:-1], path_names[1:-1]):
            if not any(node["id"] == node_id for node in nodes):
                nodes.append({
                    "id": node_id,
                    "label": node_name,
                    "color": "#8e44ad",
                    "size": 20,
                    "shape": "dot",
                })
        for idx in range(len(path) - 1):
            relation_types = "、".join(shortest_path.get("edge_relations", [])[idx]) if idx < len(shortest_path.get("edge_relations", [])) else "关联"
            add_edge(path[idx], path[idx + 1], relation_types, "#e67e22", width=4, roundness=0.12)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>双节点关系分析</title>
    <script src="https://cdn.bootcdn.net/ajax/libs/vis-network/9.1.2/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{ margin: 0; font-family: "Microsoft YaHei", sans-serif; background: #fafafa; }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            padding: 12px 16px 0;
            font-size: 12px;
            color: #666;
        }}
        .legend span::before {{
            content: "";
            display: inline-block;
            width: 14px;
            height: 3px;
            margin-right: 6px;
            vertical-align: middle;
            background: currentColor;
        }}
        #network {{ width: 100%; height: 560px; }}
    </style>
</head>
<body>
    <div class="legend">
        <span style="color:#2ecc71">资金</span>
        <span style="color:#3498db">聊天</span>
        <span style="color:#f39c12">通话</span>
        <span style="color:#9b59b6">共同证据</span>
        <span style="color:#e67e22">最短路径</span>
        <span style="color:#95a5a6">共同联系人</span>
    </div>
    <div id="network"></div>
    <script>
        const nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
        const edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
        const container = document.getElementById("network");
        const data = {{ nodes, edges }};
        const options = {{
            layout: {{
                improvedLayout: true
            }},
            physics: {{
                solver: "forceAtlas2Based",
                forceAtlas2Based: {{
                    gravitationalConstant: -80,
                    centralGravity: 0.01,
                    springLength: 200,
                    springConstant: 0.08
                }},
                stabilization: {{ iterations: 150 }}
            }},
            interaction: {{
                hover: true,
                navigationButtons: true,
                keyboard: true
            }},
            nodes: {{
                borderWidth: 2,
                font: {{ size: 14, color: "#222" }}
            }},
            edges: {{
                selectionWidth: 4
            }}
        }};
        new vis.Network(container, data, options);
    </script>
</body>
</html>
"""
    return html


def analyze_pair_relationship(user_a: str, user_b: str) -> dict:
    """分析两个节点之间的多维关系。"""
    persons, id_to_name, name_to_id = _load_person_maps()
    person_a_name = _person_display(user_a, id_to_name)
    person_b_name = _person_display(user_b, id_to_name)

    direct_tx_df = _query_direct_transactions(user_a, user_b, person_a_name, person_b_name)
    chat_df = _query_chat_relation(user_a, user_b)
    call_df = _query_call_relation(user_a, user_b)
    shared_evidence_df = _query_shared_evidence(user_a, user_b)

    tx_contacts_a = _collect_tx_contacts(user_a, person_a_name, id_to_name, name_to_id)
    tx_contacts_b = _collect_tx_contacts(user_b, person_b_name, id_to_name, name_to_id)
    chat_contacts_a = _collect_chat_contacts(user_a, id_to_name)
    chat_contacts_b = _collect_chat_contacts(user_b, id_to_name)
    call_contacts_a = _collect_call_contacts(user_a, id_to_name)
    call_contacts_b = _collect_call_contacts(user_b, id_to_name)

    merged_a = defaultdict(dict)
    merged_b = defaultdict(dict)
    for source, target in [
        (tx_contacts_a, merged_a), (chat_contacts_a, merged_a), (call_contacts_a, merged_a),
        (tx_contacts_b, merged_b), (chat_contacts_b, merged_b), (call_contacts_b, merged_b),
    ]:
        for key, value in source.items():
            target[key].update(value)

    common_contacts = _merge_common_contacts(merged_a, merged_b)

    relation_graph = _build_relation_graph(id_to_name, name_to_id)
    shortest_path = {"exists": False, "length": 0, "path": [], "path_names": [], "edge_relations": []}
    if user_a in relation_graph and user_b in relation_graph:
        try:
            path = nx.shortest_path(relation_graph, user_a, user_b)
            shortest_path["exists"] = True
            shortest_path["path"] = path
            shortest_path["length"] = len(path)
            shortest_path["path_names"] = [_person_display(node, id_to_name) for node in path]
            edge_relations = []
            for i in range(len(path) - 1):
                relation_types = sorted(list(relation_graph[path[i]][path[i + 1]].get("relations", [])))
                edge_relations.append(relation_types)
            shortest_path["edge_relations"] = edge_relations
        except nx.NetworkXNoPath:
            pass

    direct_tx = _summarize_direct_transactions(direct_tx_df, user_a, user_b, person_a_name, person_b_name)
    chat = _summarize_chat_relation(chat_df)
    call = _summarize_call_relation(call_df)
    shared_evidence = _summarize_shared_evidence(shared_evidence_df)
    score_info = _calculate_relation_score(direct_tx, chat, call, common_contacts, shortest_path, shared_evidence)
    summary = _build_summary_text(person_a_name, person_b_name, direct_tx, chat, call, common_contacts, shortest_path, shared_evidence, score_info)

    analysis = {
        "person_a": {"user_id": user_a, "name": person_a_name},
        "person_b": {"user_id": user_b, "name": person_b_name},
        "direct_transactions": direct_tx,
        "chat_relation": chat,
        "call_relation": call,
        "common_contacts": common_contacts,
        "shortest_path": shortest_path,
        "shared_evidence": shared_evidence,
        "relation_score": score_info,
        "relation_summary": summary,
    }
    analysis["relationship_graph_html"] = _generate_relationship_html(analysis)
    return analysis
