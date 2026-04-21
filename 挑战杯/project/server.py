"""FastAPI 后端主入口 — 提供 REST API"""
import json
import math
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, Form
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import tempfile
import sys
import pandas as pd
import hashlib
import os
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from src.database import (
    init_db, get_db_stats, get_all_persons, get_persons_with_transactions,
    get_person_transactions, clear_db, get_counterpart_summary, get_bank_cards,
    get_all_cases, create_case, get_case_info, get_case_evidences, get_person_evidences,
    get_conn
)
from src.ingest import ingest_tenpay_data, auto_discover_and_ingest
from src.anomaly import run_all_detections, get_risk_summary
from src.graph_analysis import (
    build_transaction_graph, get_network_metrics, find_bridge_accounts,
    find_fund_cycles, get_top_counterparts, generate_pyvis_html,
    analyze_pair_relationship
)
from src.profiler import generate_profile, generate_report_text
from src.agent import chat_with_agent, chat_with_agent_stream, _resolve_user_id
from src.evidence_import import import_evidence
from src.unified_import import UnifiedImportService
from config import LLM_PROVIDERS, get_resource_path

# 初始化
init_db()

# ==================== 缓存机制 ====================
# 简单的内存缓存（生产环境建议使用 Redis）
_cache = {}
_cache_ttl = 300  # 缓存5分钟
 
 
# 临时占位函数，实际路由在后文注册
def api_relationship(user_a: str = Query(...), user_b: str = Query(...)):
    """分析两个节点之间的关系。"""
    uid_a = _resolve_user_id(user_a)
    uid_b = _resolve_user_id(user_b)
    if uid_a == uid_b:
        raise HTTPException(status_code=400, detail="请选择两个不同的节点")

    cache_key = _cache_key("relationship", uid_a, uid_b)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        result = _clean_for_json(analyze_pair_relationship(uid_a, uid_b))
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
app.get("/api/relationship")(api_relationship)
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
def api_stats(case_id: Optional[str] = Query(None)):
    """数据库统计（支持按案件过滤，带缓存）"""
    cache_key = _cache_key("stats", case_id or "all")
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    if case_id:
        # 返回指定案件的统计
        conn = get_conn()
        stats = {
            "person_count": conn.execute("SELECT COUNT(*) FROM persons WHERE case_id = ?", [case_id]).fetchone()[0],
            "card_count": conn.execute("SELECT COUNT(*) FROM bank_cards WHERE user_id IN (SELECT user_id FROM persons WHERE case_id = ?)", [case_id]).fetchone()[0],
            "tx_count": conn.execute("SELECT COUNT(*) FROM transactions WHERE case_id = ?", [case_id]).fetchone()[0],
            "case_count": 1,
            "evidence_count": conn.execute("SELECT COUNT(*) FROM evidence_meta WHERE case_id = ?", [case_id]).fetchone()[0],
        }
        conn.close()
    else:
        # 返回全部统计
        stats = get_db_stats()

    _set_cache(cache_key, stats)
    return stats


@app.get("/api/persons")
def api_persons(
    case_id: Optional[str] = Query(None),
    with_transactions: bool = True,
    exclude_companies: bool = True
):
    """
    人员列表（支持按案件过滤，带缓存）
    case_id: 案件ID（可选）
    with_transactions: 是否只返回有交易记录的人员（默认true）
    exclude_companies: 是否排除企业（默认true）
    """
    # 缓存键包含所有参数
    cache_key = _cache_key("persons", case_id or "all", with_transactions, exclude_companies)
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    if with_transactions:
        df = get_persons_with_transactions(exclude_companies=exclude_companies)
    else:
        df = get_all_persons()

    # 按案件过滤
    if case_id and not df.empty:
        df = df[df['case_id'] == case_id]

    result = _df_to_records(df)
    _set_cache(cache_key, result)
    return result


@app.post("/api/evidence/import")
async def import_evidence_file(
    file: UploadFile = File(...),
    case_id: int = Form(...),
    evidence_type: str = Form("auto"),
    description: str = Form("")
):
    """统一证据导入接口"""

    # 保存上传文件到临时目录
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    # 使用统一导入服务
    service = UnifiedImportService(case_id, uploader=" investigator")
    result = service.import_file(
        temp_path,
        evidence_type=evidence_type,
        description=description
    )

    # 清理临时文件
    os.remove(temp_path)

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result
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


# ==================== 案件管理 ====================

@app.post("/api/cases")
def api_create_case(case_id: str = Query(...), case_name: str = Query(...)):
    """创建新案件"""
    result = create_case(case_id, case_name)
    clear_cache()
    return result


@app.get("/api/cases")
def api_list_cases():
    """获取所有案件列表（优化版）"""
    cache_key = _cache_key("cases_list")
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    df = get_all_cases()
    result = _df_to_records(df)

    _set_cache(cache_key, result)
    return result


@app.get("/api/cases/{case_id}")
def api_get_case(case_id: str):
    """获取案件详情"""
    case_info = get_case_info(case_id)
    if not case_info:
        raise HTTPException(status_code=404, detail="案件不存在")
    return case_info


# ==================== 证据管理 ====================

@app.post("/api/evidence/upload")
async def api_upload_evidence(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    evidence_type: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    related_persons: Optional[str] = Form(None),  # JSON字符串
    event_time: Optional[str] = Form(None),
    extract_time: Optional[str] = Form(None)
):
    """上传证据文件（全自动识别）"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # 手动信息（如果用户提供）
        manual_info = {}
        if evidence_type:
            manual_info['evidence_type'] = evidence_type
        if title:
            manual_info['title'] = title
        if related_persons:
            manual_info['related_persons'] = json.loads(related_persons)
        if event_time:
            manual_info['event_time'] = event_time
        if extract_time:
            manual_info['extract_time'] = extract_time

        # 如果没有提供case_id，生成一个默认的
        actual_case_id = case_id or f"AUTO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        result = import_evidence(
            file_path=tmp_path,
            case_id=actual_case_id,
            manual_info=manual_info if manual_info else None
        )

        clear_cache()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        import os
        os.unlink(tmp_path)


@app.get("/api/evidence/case/{case_id}")
def api_get_case_evidences(case_id: str):
    """获取案件的所有证据"""
    df = get_case_evidences(case_id)
    return _df_to_records(df)


@app.get("/api/evidence/person/{person_id}")
def api_get_person_evidences(person_id: str):
    """获取某人相关的所有证据"""
    df = get_person_evidences(person_id)
    return _df_to_records(df)


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


@app.post("/api/investigation_profile")
def api_investigation_profile(case_id: str = Form(...), user_id: str = Form(...)):
    """生成检察侦查画像报告（基于全案证据的AI深度分析）"""
    try:
        from src.investigation_profiler import generate_investigation_report

        # 解析user_id
        uid = _resolve_user_id(user_id)

        # 生成报告
        report = generate_investigation_report(case_id, uid)

        return {
            "success": True,
            "report": report,
            "case_id": case_id,
            "user_id": uid,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")


# ==================== AI Agent ====================

class ChatRequest(BaseModel):
    messages: list
    provider_id: str = "anthropic"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    """AI Agent 对话（非流式）"""
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


@app.post("/api/chat/stream")
async def api_chat_stream(req: ChatRequest):
    """AI Agent 对话（流式）"""
    import json

    async def generate():
        try:
            for chunk in chat_with_agent_stream(
                messages=req.messages,
                provider_id=req.provider_id,
                api_key=req.api_key or None,
                model=req.model or None,
                base_url=req.base_url or None,
            ):
                # 使用SSE格式
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            error_chunk = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/providers")
def api_providers():
    """获取支持的LLM厂商列表"""
    return {pid: {"name": p["name"], "models": p["models"], "default_model": p["default_model"]}
            for pid, p in LLM_PROVIDERS.items()}


# ==================== 前端静态文件 ====================

FRONTEND_DIR = get_resource_path("frontend")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# 静态资源和 SPA fallback 用 mount 放在最后
# mount 必须在所有 /api 路由之后, 否则会覆盖
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import sys
    import uvicorn

    # Windows 环境设置 UTF-8 编码
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        timeout_keep_alive=300,
        log_level="info"
    )
