"""基于 NetworkX 的关系图谱分析模块"""
import networkx as nx
import pandas as pd
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


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
    """生成 PyVis 交互式图谱 HTML"""
    from pyvis.network import Network

    net = Network(height="600px", width="100%", directed=True, bgcolor="#ffffff")
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=200)

    # 只保留与target有直接关系的节点(1跳邻居), 以及邻居间的关系
    neighbors = set(list(G.successors(target)) + list(G.predecessors(target)))
    subgraph_nodes = {target} | neighbors

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
        net.add_node(node, label=label, title=title, color=color, size=size)

    for src, dst in G.edges():
        if src in subgraph_nodes and dst in subgraph_nodes:
            edge_data = G[src][dst]
            weight = edge_data["weight"]
            count = edge_data["count"]
            # 边粗细反映金额
            width = max(1, min(10, weight / 5000))
            # 金额大的用红色
            color = "#e74c3c" if weight >= 10000 else "#7f8c8d"
            title = f"金额: {weight:.0f}元, 笔数: {count}"
            net.add_edge(src, dst, width=width, color=color, title=title,
                        arrows="to", label=f"{weight:.0f}")

    if output_path:
        net.save_graph(output_path)
        return output_path
    else:
        return net.generate_html()
