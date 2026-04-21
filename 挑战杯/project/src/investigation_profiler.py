"""检察侦查画像生成模块 - 基于全案证据的深度分析"""
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LLM_PROVIDERS, get_provider_api_key
from src.database import (
    get_all_persons, get_person_transactions, get_all_transactions,
    get_counterpart_summary, get_bank_cards, get_conn
)


# ============================================================
# 检察侦查画像专用提示词
# ============================================================

INVESTIGATION_PROFILE_PROMPT = """你是一个服务于中国检察机关的资深职务犯罪侦查专家与犯罪心理学分析师。你的任务是根据系统提供的案件全部证据数据，生成一份精准、客观、可以直接指导一线办案和审讯的《目标人物画像报告》。你的语言必须严谨、精炼，具备法言法语特征，严禁使用模糊或情绪化的修饰词。

## 全局原则
1. **绝对禁止编造数据**：你只能引用提供的真实证据数据。如果某个模块缺少必要数据，明确说明"数据不足，无法分析"，而不是推测或编造。
2. **证据溯源**：每个结论后必须标注数据来源（如：证据ID、具体时间、金额等）。
3. **多源印证**：优先寻找不同证据类型之间的相互印证（如：资金转账时间与聊天记录吻合）。
4. **不做推定**：只描述异常模式，使用"疑似"、"建议核查"等措辞，不直接认定犯罪。

---

## 模块一：目标人物性格与心理底色画像

### 输入数据源
- 目标人物的微信/短信等社交聊天文本记录（重点关注用词习惯、高频词）
- 法院/公安内网办案系统的操作日志时间戳（重点关注工作习惯，如是否在深夜或非工作日异常操作）
- 供述笔录内容（语气、辩解逻辑）

### 分析逻辑
1. **性格分型**：基于"大五人格模型"或"DISC性格测试"，分析其行事风格（如：严谨防卫型、胆大支配型、圆滑规避型）
2. **反侦查意识**：提取文本中的"隐语/暗语"频率，评估其反侦查意识等级（高/中/低）
3. **情感软肋**：分析其聊天对象的身份与情绪波动点，寻找其情感软肋（如：极度保护子女、对情妇有补偿心理、极度看重个人仕途）

### 输出规范
**字数限制**：150-200字以内。

**格式要求**：
```markdown
### 一、目标人物性格与心理底色

**性格基础分型**：[一句话结论]
**证据支撑**：[具体证据ID或数据]

**反侦查意识等级**：高/中/低
**证据支撑**：[具体证据，如："聊天记录中高频使用'布料'、'喝茶'等替代性隐语"]

**核心情感软肋**：[一句话结论]
**证据支撑**：[具体证据]
```

---

## 模块二：异常交往人员图谱（利益代持人与掮客锁定）

### 输入数据源
- 目标人物近期的通讯通话记录（频次与时长）
- 案件相关人员的时空轨迹数据
- 涉案当事人及相关人员名单
- 资金往来对手方信息

### 分析逻辑
1. **时空碰撞**：筛选出在"案件关键节点（如评估、拍卖、立案前）"与目标人物出现过"轨迹重合（同地同时）"或"通讯激增"的非亲属人员
2. **角色定性预判**：
   - 如果该异常人员是律师/商人，标记为疑似"司法掮客"
   - 如果是无正常高收入来源的年轻女性/远房亲属，标记为疑似"利益代持人（白手套）"
3. **资金关联**：检查异常人员是否与目标人物存在频繁资金往来

### 输出规范
**字数限制**：每个异常人员描述不超过50字。

**格式要求**：仅输出排名前 2-3 位的最高危异常联系人。
```markdown
### 二、异常交往人员图谱

**高危关系人 TOP 3**：

1. **[姓名]** | 疑似[角色标签] | [异常行为摘要]
   - **时空特征**：[具体时间+地点重合情况]
   - **通讯特征**：[通话频次/时长异常]
   - **资金关联**：[是否存在资金往来]

2. [同上格式]

3. [同上格式]
```

---

## 模块三：异常交易特征与资金漏斗

### 输入数据源
- 目标人物本人的银行与第三方支付流水
- 模块二中锁定的"异常交往人员"的银行流水
- 案件相关的所有交易记录

### 分析逻辑
1. **异常特征识别**：忽略正常生活开销，重点排查：
   - "资金快进快出"
   - "大额整数转账"
   - "多层嵌套过账（对公转对公再转对私）"
2. **时序关联**：比对行贿方资金转出的时间点，与目标人物在系统"违规操作/篡改文书"的时间点，是否存在因果时序关联
3. **资金流向追踪**：构建资金流转路径图

### 输出规范
**字数限制**：100-150字。

**格式要求**：
```markdown
### 三、异常交易特征与资金漏斗

发现 [数量] 条高度可疑资金链：

**资金链1**：涉案金额 XXX 万元
- **流转路径**：A（[身份]）→ B（[身份]）→ C（[身份]）
- **异常特征**：[具体描述，如："多层嵌套洗钱特征"/"化整为零特征"]
- **时序关联**：[与案件关键事件的时间对应关系]
- **证据支撑**：[交易记录ID/时间/金额]

[如有多条资金链，继续列举]
```

---

## 模块四：实战审讯突破策略生成

### 输入数据源
- 模块一生成的心理软肋与反侦查等级
- 模块二、三中得出的铁证（最难以解释的人际关系或异常资金）
- 供述笔录中的辩解逻辑

### 分析逻辑
1. **避其锋芒**：识别嫌疑人最容易狡辩的领域（通常是其滥用职权时的"业务自由裁量权"或"程序瑕疵"），建议审讯时避开或延后触碰
2. **降维打击**：结合其情感软肋和资金铁证，设计一个让其无法圆谎、瞬间崩溃的切入点（例如直接抛出其情妇的海外资产或洗钱证据）
3. **话术建议**：根据性格分型给出具体审讯话术

### 输出规范
**字数限制**：100-150字。

**格式要求**：
```markdown
### 四、实战审讯突破策略

**避开的锋芒**：[内容，如："避免纠缠其业务自由裁量权的合理性"]

**降维打击点**：[具体切入点]
- **铁证**：[具体证据，如："其配偶账户在XX日期收到来自XX的XX万元转账"]
- **预设话术**：根据其[性格特征]，建议使用[具体话术]
- **崩溃触发点**：[预判其心理防线最薄弱的点]

**后续追问路线**：[如果突破后，应追问的关键问题]
```

---

## 最终输出格式

你的输出必须严格遵循以下Markdown格式：

```markdown
# 检察侦查画像报告

**案件ID**：[case_id]
**目标人物**：[姓名] ([user_id])
**生成时间**：[当前时间]

---

### 一、目标人物性格与心理底色
[按模块一格式输出]

---

### 二、异常交往人员图谱
[按模块二格式输出]

---

### 三、异常交易特征与资金漏斗
[按模块三格式输出]

---

### 四、实战审讯突破策略
[按模块四格式输出]

---

### 五、综合风险评级与侦查建议

**综合风险等级**：高/中/低
**核心侦查方向**：[2-3条具体建议]
**证据补强建议**：[需要进一步收集的证据类型]
```

---

## 特别提醒
- 如果某个模块的数据完全缺失（如：无聊天记录、无轨迹数据），明确说明"该模块数据不足，无法进行分析"，不要强行输出。
- 所有结论必须基于提供的数据，禁止推测或编造任何信息。
- 保持专业、客观、严谨的法律语言风格。
"""


# ============================================================
# 数据收集函数 - 收集全案证据
# ============================================================

def collect_case_all_evidence(case_id: str, target_user_id: str) -> dict:
    """
    收集案件的所有证据数据（不限于目标人物），并标注与目标人物的关联

    Args:
        case_id: 案件ID
        target_user_id: 目标人物ID

    Returns:
        dict: 包含所有证据数据的字典
    """
    conn = get_conn()
    data = {}

    # 1. 案件基本信息
    case_query = "SELECT * FROM cases WHERE case_id = ?"
    case_df = pd.read_sql(case_query, conn, params=[case_id])
    data['case_info'] = case_df.to_dict('records')[0] if not case_df.empty else {}

    # 2. 案件所有涉案人员
    persons_query = "SELECT * FROM persons WHERE case_id = ?"
    persons_df = pd.read_sql(persons_query, conn, params=[case_id])
    data['all_persons'] = persons_df.to_dict('records')

    # 获取目标人物信息
    target_person = persons_df[persons_df['user_id'] == target_user_id]
    data['target_person'] = target_person.to_dict('records')[0] if not target_person.empty else {}

    # 3. 案件所有交易记录（全案）
    tx_query = "SELECT * FROM transactions WHERE case_id = ? ORDER BY trade_time"
    all_tx_df = pd.read_sql(tx_query, conn, params=[case_id])
    data['all_transactions'] = all_tx_df.to_dict('records')

    # 标注与目标人物相关的交易
    target_tx = all_tx_df[
        (all_tx_df['user_id'] == target_user_id) |
        (all_tx_df['counterpart_id'] == target_user_id)
    ]
    data['target_transactions'] = target_tx.to_dict('records')

    # 4. 案件所有聊天记录（全案）
    chat_query = "SELECT * FROM chat_records WHERE evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?) ORDER BY send_time"
    all_chat_df = pd.read_sql(chat_query, conn, params=[case_id])
    data['all_chat_records'] = all_chat_df.to_dict('records')

    # 标注目标人物的聊天
    target_chat = all_chat_df[
        (all_chat_df['sender_id'] == target_user_id) |
        (all_chat_df['receiver_id'] == target_user_id)
    ]
    data['target_chat_records'] = target_chat.to_dict('records')

    # 5. 案件所有通话记录（全案）
    call_query = "SELECT * FROM call_records WHERE evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?) ORDER BY call_time"
    all_call_df = pd.read_sql(call_query, conn, params=[case_id])
    data['all_call_records'] = all_call_df.to_dict('records')

    # 标注目标人物的通话
    target_call = all_call_df[
        (all_call_df['caller_id'] == target_user_id) |
        (all_call_df['callee_id'] == target_user_id)
    ]
    data['target_call_records'] = target_call.to_dict('records')

    # 6. 案件所有轨迹记录（全案）
    loc_query = "SELECT * FROM location_records WHERE evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?) ORDER BY record_time"
    all_loc_df = pd.read_sql(loc_query, conn, params=[case_id])
    data['all_location_records'] = all_loc_df.to_dict('records')

    # 标注目标人物的轨迹
    target_loc = all_loc_df[all_loc_df['person_id'] == target_user_id]
    data['target_location_records'] = target_loc.to_dict('records')

    # 7. 案件所有系统日志（全案）
    log_query = "SELECT * FROM system_logs WHERE evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?) ORDER BY log_time"
    all_log_df = pd.read_sql(log_query, conn, params=[case_id])
    data['all_system_logs'] = all_log_df.to_dict('records')

    # 标注目标人物的系统日志
    target_log = all_log_df[all_log_df['person_id'] == target_user_id]
    data['target_system_logs'] = target_log.to_dict('records')

    # 8. 案件所有供述笔录（全案）
    stmt_query = """
        SELECT s.*, e.title, e.upload_time
        FROM statements s
        JOIN evidence_meta e ON s.evidence_id = e.evidence_id
        WHERE e.case_id = ?
    """
    all_stmt_df = pd.read_sql(stmt_query, conn, params=[case_id])
    data['all_statements'] = all_stmt_df.to_dict('records')

    # 标注目标人物的供述
    target_stmt = all_stmt_df[all_stmt_df['person_id'] == target_user_id]
    data['target_statements'] = target_stmt.to_dict('records')

    # 9. 案件所有文书证据（全案）
    doc_query = """
        SELECT d.*, e.title, e.upload_time, e.evidence_type
        FROM documents d
        JOIN evidence_meta e ON d.evidence_id = e.evidence_id
        WHERE e.case_id = ?
    """
    all_doc_df = pd.read_sql(doc_query, conn, params=[case_id])
    data['all_documents'] = all_doc_df.to_dict('records')

    # 10. 案件所有银行卡信息（全案）
    card_query = """
        SELECT bc.*, p.name as person_name
        FROM bank_cards bc
        JOIN persons p ON bc.user_id = p.user_id
        WHERE p.case_id = ?
    """
    all_card_df = pd.read_sql(card_query, conn, params=[case_id])
    data['all_bank_cards'] = all_card_df.to_dict('records')

    # 标注目标人物的银行卡
    target_card = all_card_df[all_card_df['user_id'] == target_user_id]
    data['target_bank_cards'] = target_card.to_dict('records')

    # 11. 证据元数据汇总（全案）
    evidence_meta_query = """
        SELECT evidence_id, evidence_type, title, event_time, extract_time, upload_time, ai_summary
        FROM evidence_meta
        WHERE case_id = ?
        ORDER BY upload_time DESC
    """
    evidence_meta_df = pd.read_sql(evidence_meta_query, conn, params=[case_id])
    data['all_evidence_meta'] = evidence_meta_df.to_dict('records')

    conn.close()

    return data


def analyze_spatiotemporal_collision(case_id: str, target_user_id: str, time_threshold_hours: int = 2, distance_threshold_meters: int = 500) -> list:
    """
    时空碰撞分析：找出与目标人物在相近时空出现的其他人员

    Args:
        case_id: 案件ID
        target_user_id: 目标人物ID
        time_threshold_hours: 时间阈值（小时）
        distance_threshold_meters: 距离阈值（米）

    Returns:
        list: 碰撞事件列表
    """
    conn = get_conn()

    # 获取目标人物的轨迹
    target_loc_query = """
        SELECT * FROM location_records
        WHERE person_id = ? AND evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?)
        ORDER BY record_time
    """
    target_loc_df = pd.read_sql(target_loc_query, conn, params=[target_user_id, case_id])

    if target_loc_df.empty:
        conn.close()
        return []

    # 获取其他人员的轨迹
    other_loc_query = """
        SELECT * FROM location_records
        WHERE person_id != ? AND evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?)
        ORDER BY record_time
    """
    other_loc_df = pd.read_sql(other_loc_query, conn, params=[target_user_id, case_id])

    conn.close()

    if other_loc_df.empty:
        return []

    # 分析碰撞
    collisions = []

    for _, target_row in target_loc_df.iterrows():
        target_time = pd.to_datetime(target_row['record_time'])
        target_lat = target_row['latitude']
        target_lon = target_row['longitude']

        # 查找时间窗口内的其他人员轨迹
        time_start = target_time - timedelta(hours=time_threshold_hours)
        time_end = target_time + timedelta(hours=time_threshold_hours)

        for _, other_row in other_loc_df.iterrows():
            other_time = pd.to_datetime(other_row['record_time'])

            # 时间匹配
            if time_start <= other_time <= time_end:
                other_lat = other_row['latitude']
                other_lon = other_row['longitude']

                # 简单的距离计算（近似，实际应使用Haversine公式）
                # 1度经纬度约等于111km
                lat_diff = abs(target_lat - other_lat) * 111000
                lon_diff = abs(target_lon - other_lon) * 111000 * 0.9  # 考虑纬度影响
                distance = (lat_diff**2 + lon_diff**2)**0.5

                # 距离匹配
                if distance <= distance_threshold_meters:
                    collisions.append({
                        'other_person_id': other_row['person_id'],
                        'target_time': str(target_time),
                        'other_time': str(other_time),
                        'time_diff_minutes': abs((other_time - target_time).total_seconds() / 60),
                        'target_location': target_row['location_name'],
                        'other_location': other_row['location_name'],
                        'distance_meters': int(distance),
                        'target_lat': target_lat,
                        'target_lon': target_lon,
                        'other_lat': other_lat,
                        'other_lon': other_lon
                    })

    # 按人员聚合
    collision_summary = {}
    for c in collisions:
        pid = c['other_person_id']
        if pid not in collision_summary:
            collision_summary[pid] = {
                'person_id': pid,
                'collision_count': 0,
                'collision_events': []
            }
        collision_summary[pid]['collision_count'] += 1
        collision_summary[pid]['collision_events'].append(c)

    # 转换为列表并排序
    result = sorted(collision_summary.values(), key=lambda x: x['collision_count'], reverse=True)

    return result


def analyze_high_frequency_contacts(case_id: str, target_user_id: str, top_n: int = 10) -> list:
    """
    分析高频联系人（通话频次、时长、深夜通话等）

    Args:
        case_id: 案件ID
        target_user_id: 目标人物ID
        top_n: 返回前N个高频联系人

    Returns:
        list: 高频联系人列表
    """
    conn = get_conn()

    # 查询目标人物的所有通话记录
    call_query = """
        SELECT * FROM call_records
        WHERE (caller_id = ? OR callee_id = ?)
        AND evidence_id IN (SELECT evidence_id FROM evidence_meta WHERE case_id = ?)
    """
    call_df = pd.read_sql(call_query, conn, params=[target_user_id, target_user_id, case_id])

    conn.close()

    if call_df.empty:
        return []

    # 确定对方ID
    call_df['other_person_id'] = call_df.apply(
        lambda row: row['callee_id'] if row['caller_id'] == target_user_id else row['caller_id'],
        axis=1
    )

    # 按对方ID聚合
    contact_stats = []

    for person_id in call_df['other_person_id'].unique():
        person_calls = call_df[call_df['other_person_id'] == person_id]

        # 统计深夜通话（0:00-6:00）
        person_calls['call_hour'] = pd.to_datetime(person_calls['call_time']).dt.hour
        night_calls = person_calls[person_calls['call_hour'].between(0, 6)]

        stats = {
            'person_id': person_id,
            'total_calls': len(person_calls),
            'total_duration': person_calls['duration'].sum(),
            'avg_duration': person_calls['duration'].mean(),
            'night_calls': len(night_calls),
            'first_call_time': person_calls['call_time'].min(),
            'last_call_time': person_calls['call_time'].max()
        }

        contact_stats.append(stats)

    # 按通话次数排序
    result = sorted(contact_stats, key=lambda x: x['total_calls'], reverse=True)[:top_n]

    return result


# ============================================================
# AI 画像生成主函数
# ============================================================

def generate_investigation_report(case_id: str, target_user_id: str) -> str:
    """
    生成完整的检察侦查画像报告

    Args:
        case_id: 案件ID
        target_user_id: 目标人物ID

    Returns:
        str: Markdown格式的完整报告
    """
    # 1. 收集全案证据数据
    evidence_data = collect_case_all_evidence(case_id, target_user_id)

    # 2. 进行高级分析
    collision_analysis = analyze_spatiotemporal_collision(case_id, target_user_id)
    contact_analysis = analyze_high_frequency_contacts(case_id, target_user_id)

    # 3. 构建提交给AI的数据包（包含全案数据）
    ai_input_data = {
        "案件基本信息": evidence_data['case_info'],
        "目标人物信息": evidence_data['target_person'],
        "案件涉案人员列表": evidence_data['all_persons'],

        # === 银行卡信息（全案）===
        "全案银行卡信息": evidence_data['all_bank_cards'],

        # === 交易记录（全案，限制条数避免超token）===
        "全案交易记录": evidence_data['all_transactions'][:200] if evidence_data['all_transactions'] else [],
        "交易记录说明": f"全案共{len(evidence_data['all_transactions'])}笔交易，已提供前200笔用于分析",

        # === 聊天记录（全案）===
        "全案聊天记录": evidence_data['all_chat_records'][:100] if evidence_data['all_chat_records'] else [],
        "聊天记录说明": f"全案共{len(evidence_data['all_chat_records'])}条聊天，已提供前100条用于分析",

        # === 通话记录（全案）===
        "全案通话记录": evidence_data['all_call_records'][:100] if evidence_data['all_call_records'] else [],
        "通话记录说明": f"全案共{len(evidence_data['all_call_records'])}条通话，已提供前100条",
        "高频联系人分析": contact_analysis,

        # === 轨迹记录（全案）===
        "全案轨迹记录": evidence_data['all_location_records'][:100] if evidence_data['all_location_records'] else [],
        "轨迹记录说明": f"全案共{len(evidence_data['all_location_records'])}条轨迹，已提供前100条",
        "时空碰撞分析": collision_analysis[:5] if collision_analysis else [],

        # === 系统日志（全案）===
        "全案系统日志": evidence_data['all_system_logs'][:100] if evidence_data['all_system_logs'] else [],
        "系统日志说明": f"全案共{len(evidence_data['all_system_logs'])}条日志，已提供前100条",

        # === 供述笔录（全案）===
        "全案供述笔录": [
            {
                "evidence_id": s['evidence_id'],
                "person_id": s.get('person_id'),
                "title": s['title'],
                "statement_type": s['statement_type'],
                "content_preview": s['content'][:1500] if s.get('content') else "",
                "upload_time": s['upload_time']
            }
            for s in evidence_data['all_statements']
        ] if evidence_data['all_statements'] else [],

        # === 文书证据（全案）===
        "全案文书证据": [
            {
                "title": d['title'],
                "doc_subtype": d.get('doc_subtype', ''),
                "evidence_type": d.get('evidence_type', ''),
                "content_preview": d['content'][:800] if d.get('content') else "",
                "upload_time": d['upload_time']
            }
            for d in evidence_data['all_documents']
        ] if evidence_data['all_documents'] else [],

        # === 证据总览 ===
        "证据总览": {
            "证据总数": len(evidence_data['all_evidence_meta']),
            "证据类型分布": {},
            "涉案人员数": len(evidence_data['all_persons'])
        }
    }

    # 统计证据类型分布
    if evidence_data.get('all_evidence_meta'):
        from collections import Counter
        evidence_types = [e['evidence_type'] for e in evidence_data['all_evidence_meta'] if e.get('evidence_type')]
        ai_input_data["证据总览"]["证据类型分布"] = dict(Counter(evidence_types))

    # 4. 构建完整的提示词
    user_prompt = f"""请基于以下案件全部证据数据，生成目标人物的检察侦查画像报告。

## 证据数据

{json.dumps(ai_input_data, ensure_ascii=False, indent=2)}

## 任务要求

请严格按照系统提示词中的四模块格式，生成完整的检察侦查画像报告。注意：

1. 必须基于提供的真实数据，禁止编造
2. 每个结论后标注证据来源
3. 如果某模块数据不足，明确说明"数据不足"
4. 优先寻找多源证据的印证关系
5. 使用严谨的法律语言

请开始生成报告。
"""

    # 5. 调用AI生成报告（使用 Qwen-Plus）
    try:
        from openai import OpenAI

        # 使用通义千问 Qwen-Plus
        api_key = get_provider_api_key("qwen")
        if not api_key:
            return "错误：未配置通义千问 API Key，无法生成报告。请在环境变量中设置 QWEN_API_KEY。"

        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        # 构建消息（System + User）
        messages = [
            {"role": "system", "content": INVESTIGATION_PROFILE_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            max_tokens=8192,  # 增加输出长度限制
            temperature=0.7,
        )

        # 提取文本内容
        report_text = response.choices[0].message.content

        return report_text

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return f"生成报告时发生错误：{str(e)}\n\n详细错误:\n{error_detail}\n\n请检查API配置或网络连接。"


# ============================================================
# 测试函数
# ============================================================

if __name__ == "__main__":
    # 测试用例
    test_case_id = "CASE_LIJIAN_2025"
    test_user_id = "lijian001"

    print("正在生成检察侦查画像报告...")
    report = generate_investigation_report(test_case_id, test_user_id)
    print(report)
