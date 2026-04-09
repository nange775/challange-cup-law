"""FastAPI 后端主入口 — 提供 REST API"""
import json
import math
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import sys
import pandas as pd
import hashlib

sys.path.insert(0, str(Path(__file__).parent))
from src.database import init_db, get_db_stats, get_all_persons, get_person_transactions, clear_db, get_counterpart_summary, get_bank_cards
from src.ingest import ingest_tenpay_data, auto_discover_and_ingest
from src.anomaly import run_all_detections, get_risk_summary
from src.graph_analysis import build_transaction_graph, get_network_metrics, find_bridge_accounts, find_fund_cycles, get_top_counterparts, generate_pyvis_html
from src.profiler import generate_profile, generate_report_text
from src.agent import chat_with_agent, _resolve_user_id
from config import LLM_PROVIDERS

# 初始化
init_db()

# ==================== 缓存机制 ====================
# 简单的内存缓存（生产环境建议使用 Redis）
_cache = {}
_cache_ttl = 300  # 缓存5分钟


def _cache_key(*args) -> str:
    """生成缓存键"""
    key_str = "_".join(str(a) for a in args)
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_cache(key: str):
    """获取缓存"""
    import time
    if key in _cache:
        data, timestamp = _cache[key]
        if time.time() - timestamp < _cache_ttl:
            return data
        else:
            del _cache[key]
    return None


def _set_cache(key: str, data):
    """设置缓存"""
    import time
    _cache[key] = (data, time.time())


def clear_cache():
    """清除所有缓存"""
    _cache.clear()

app = FastAPI(title="检察侦查画像系统 API", version="1.0.0")

# CORS - 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean_for_json(obj):
    """递归清理数据中的 NaN/Inf, 使其可被 JSON 序列化"""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_for_json(v) for v in obj]
    return obj


def _df_to_records(df: pd.DataFrame) -> list:
    """DataFrame 转 records, 自动处理 NaN"""
    return _clean_for_json(df.where(df.notna(), None).to_dict(orient="records"))


# ==================== 数据导入 ====================

@app.get("/api/stats")
def api_stats():
    """数据库统计"""
    return get_db_stats()


@app.get("/api/persons")
def api_persons():
    """所有人员列表"""
    df = get_all_persons()
    return _df_to_records(df)


@app.post("/api/upload")
async def api_upload(trades: UploadFile = File(...), reginfo: UploadFile = File(...)):
    """上传交易明细和注册信息文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        trades_path = Path(tmpdir) / trades.filename
        reg_path = Path(tmpdir) / reginfo.filename
        trades_path.write_bytes(await trades.read())
        reg_path.write_bytes(await reginfo.read())
        try:
            result = ingest_tenpay_data(str(trades_path), str(reg_path))
            # 清除缓存，因为数据已更新
            clear_cache()
            return result
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auto-import")
def api_auto_import(directory: str = Query(...)):
    """自动扫描目录并导入"""
    p = Path(directory)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"目录不存在: {directory}")
    results = auto_discover_and_ingest(directory)
    # 清除缓存，因为数据已更新
    clear_cache()
    return results


@app.post("/api/clear")
def api_clear():
    """清空数据库"""
    clear_db()
    # 清除所有缓存
    clear_cache()
    return {"message": "已清空"}


# ==================== 交易查询 ====================

@app.get("/api/transactions/{user_id}")
def api_transactions(
    user_id: str,
    direction: Optional[str] = None,
    purpose: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
):
    """查询用户交易记录"""
    uid = _resolve_user_id(user_id)
    df = get_person_transactions(uid)
    if df.empty:
        return []
    if direction:
        df = df[df["direction"] == direction]
    if purpose:
        df = df[df["purpose"].str.contains(purpose, na=False)]
    if start_date:
        df = df[df["trade_time"] >= start_date]
    if end_date:
        df = df[df["trade_time"] <= end_date]
    df = df.head(limit)
    df["trade_time"] = df["trade_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["amount_yuan"] = df["amount"] / 100
    return _df_to_records(df)


@app.get("/api/counterparts/{user_id}")
def api_counterparts(user_id: str, top_n: int = 20):
    """对手方汇总"""
    uid = _resolve_user_id(user_id)
    df = get_counterpart_summary(uid)
    if df.empty:
        return []
    return _df_to_records(df.head(top_n))


@app.get("/api/monthly/{user_id}")
def api_monthly(user_id: str):
    """按月统计入账/出账（带缓存）"""
    cache_key = _cache_key("monthly", user_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    uid = _resolve_user_id(user_id)
    df = get_person_transactions(uid)
    if df.empty:
        return []
    df["month"] = df["trade_time"].dt.to_period("M").astype(str)
    result = []
    for month, group in df.groupby("month"):
        income = group[group["direction"] == "入"]["amount"].sum() / 100
        expense = group[group["direction"] == "出"]["amount"].sum() / 100
        result.append({"month": month, "income": income, "expense": expense, "count": len(group)})

    _set_cache(cache_key, result)
    return result


@app.get("/api/hour-distribution/{user_id}")
def api_hour_distribution(user_id: str):
    """交易时段分布（带缓存）"""
    cache_key = _cache_key("hour_dist", user_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    uid = _resolve_user_id(user_id)
    df = get_person_transactions(uid)
    if df.empty:
        return []
    df["hour"] = df["trade_time"].dt.hour
    dist = df.groupby("hour").size().reset_index(name="count")
    result = dist.to_dict(orient="records")

    _set_cache(cache_key, result)
    return result


# ==================== 异常检测 ====================

@app.get("/api/anomaly/{user_id}")
def api_anomaly(user_id: str):
    """运行全套异常检测（带缓存）"""
    cache_key = _cache_key("anomaly", user_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    uid = _resolve_user_id(user_id)
    tx = get_person_transactions(uid)
    if tx.empty:
        return {"risk_summary": [], "details": {}}
    results = run_all_detections(tx)
    summary = get_risk_summary(results)
    details = {}
    for key, df in results.items():
        if hasattr(df, 'empty') and not df.empty:
            df_copy = df.copy()
            for col in df_copy.columns:
                if hasattr(df_copy[col], 'dt'):
                    df_copy[col] = df_copy[col].astype(str)
            details[key] = _df_to_records(df_copy)
        else:
            details[key] = []
    result = _clean_for_json({"risk_summary": summary, "details": details})

    _set_cache(cache_key, result)
    return result


# ==================== 图谱分析 ====================

@app.get("/api/graph/{user_id}")
def api_graph(user_id: str):
    """关系网络分析数据（带缓存，优化性能）"""
    cache_key = _cache_key("graph", user_id)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    uid = _resolve_user_id(user_id)
    persons = get_all_persons()
    row = persons[persons["user_id"] == uid]
    target_name = row.iloc[0]["name"] if not row.empty else uid
    tx = get_person_transactions(uid)
    if tx.empty:
        return {"metrics": {}, "bridges": [], "cycles": [], "top_contacts": [], "graph_html": ""}

    G = build_transaction_graph(tx)

    # 检查图是否有效
    if len(G.nodes()) == 0:
        return {"metrics": {}, "bridges": [], "cycles": [], "top_contacts": [],
                "graph_html": "<div style='text-align:center;padding:50px;color:#999;'>无有效交易数据</div>"}

    metrics = get_network_metrics(G, target_name)
    bridges = find_bridge_accounts(G, target_name)
    cycles = find_fund_cycles(G, target_name)
    top = get_top_counterparts(G, target_name, top_n=15)

    try:
        graph_html = generate_pyvis_html(G, target_name)
    except Exception as e:
        print(f"图谱生成失败: {e}")
        graph_html = f"<div style='text-align:center;padding:50px;color:#f56c6c;'>图谱生成失败: {str(e)}</div>"

    result = _clean_for_json({
        "metrics": metrics,
        "bridges": bridges[:10],
        "cycles": cycles[:10],
        "top_contacts": top,
        "graph_html": graph_html,
    })

    _set_cache(cache_key, result)
    return result


# ==================== 人员画像 ====================

@app.get("/api/profile/{user_id}")
def api_profile(user_id: str):
    """生成完整画像"""
    uid = _resolve_user_id(user_id)
    profile = generate_profile(uid)
    report_text = generate_report_text(profile)
    clean = {}
    for k, v in profile.items():
        if hasattr(v, 'to_dict'):
            clean[k] = _df_to_records(v)
        else:
            clean[k] = v
    clean["report_text"] = report_text
    return _clean_for_json(clean)


# ==================== AI Agent ====================

class ChatRequest(BaseModel):
    messages: list
    provider_id: str = "anthropic"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    """AI Agent 对话"""
    reply, updated = chat_with_agent(
        messages=req.messages,
        provider_id=req.provider_id,
        api_key=req.api_key or None,
        model=req.model or None,
        base_url=req.base_url or None,
    )
    # updated 中可能含有不可序列化的对象, 只保留纯文本历史
    simple_history = []
    for msg in updated:
        if isinstance(msg.get("content"), str):
            simple_history.append(msg)
    return {"reply": reply, "history": simple_history}


@app.get("/api/providers")
def api_providers():
    """获取支持的LLM厂商列表"""
    return {pid: {"name": p["name"], "models": p["models"], "default_model": p["default_model"]}
            for pid, p in LLM_PROVIDERS.items()}


# ==================== 前端静态文件 ====================

FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# 静态资源和 SPA fallback 用 mount 放在最后
# mount 必须在所有 /api 路由之后, 否则会覆盖
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
