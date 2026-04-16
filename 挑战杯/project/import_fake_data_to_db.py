"""
将生成的假数据批量导入到数据库
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from src.database import create_case, get_conn, init_db
from src.evidence_import import import_evidence

print("=== 开始导入李建案假数据到数据库 ===\n")

# 1. 初始化数据库
print("1. 初始化数据库...")
init_db()
print("   ✓ 数据库初始化完成")

# 2. 创建案件
print("\n2. 创建案件...")
case_id = "CASE_LIJIAN_2025"
result = create_case(case_id, "李建徇私枉法案")
if result['success']:
    print(f"   ✓ 案件创建成功: {case_id}")
else:
    print(f"   ✗ 案件创建失败: {result.get('error')}")

# 3. 创建涉案人员
print("\n3. 创建涉案人员...")
conn = get_conn()

persons = [
    ("lijian001", "李建", "110101198003150000", "13800001111", "2005-01-01", "嫌疑人"),
    ("wangqiang001", "王强", "110101197508200000", "13800002222", "2010-03-15", "嫌疑人"),
    ("zhaomin001", "赵敏", "110101198509100000", "13800003333", "2015-06-20", "涉案人"),
    ("lihui001", "李辉", "110101200101050000", "13800004444", "2020-01-01", "涉案人"),
    ("zhangwei001", "张伟", "110101199705120000", "13800005555", "2020-07-01", "证人"),
    # 空壳公司
    ("xingchen001", "星辰商贸有限公司", "", "", "2020-01-01", "涉案人"),
    ("yazhi001", "雅致画廊", "", "", "2018-05-01", "涉案人"),
]

for user_id, name, id_card, phone, reg_time, role in persons:
    conn.execute("""
        INSERT INTO persons (user_id, case_id, name, id_card, phone, reg_time, role)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [user_id, case_id, name, id_card, phone, reg_time, role])

conn.commit()
conn.close()
print(f"   ✓ 已创建 {len(persons)} 个涉案人员")

# 4. 导入证据文件
print("\n4. 导入证据文件...")

fake_data_dir = Path("fakedata")
evidence_files = [
    {
        "file": fake_data_dir / "资金流水_李建案.xlsx",
        "type": "流水",
        "title": "李建案资金流水（完整洗钱链路）",
        "persons": ["lijian001", "wangqiang001", "zhaomin001", "lihui001"],
        "event_time": "2025-10-12",
        "extract_time": "2025-11-20"
    },
    {
        "file": fake_data_dir / "通话记录_李建案.xlsx",
        "type": "通话",
        "title": "李建、赵敏、王强通话记录",
        "persons": ["lijian001", "zhaomin001", "wangqiang001", "lihui001"],
        "event_time": "2025-10-09",
        "extract_time": "2025-11-20"
    },
    {
        "file": fake_data_dir / "微信聊天记录_李建赵敏.xlsx",
        "type": "聊天",
        "title": "李建与赵敏微信聊天记录（含暗语）",
        "persons": ["lijian001", "zhaomin001"],
        "event_time": "2025-10-10",
        "extract_time": "2025-11-18"
    },
    {
        "file": fake_data_dir / "系统操作日志_案管系统.xlsx",
        "type": "日志",
        "title": "案管系统VPN登录及操作日志",
        "persons": ["lijian001", "zhangwei001"],
        "event_time": "2025-10-10",
        "extract_time": "2025-11-20"
    },
    {
        "file": fake_data_dir / "行动轨迹_李建案.xlsx",
        "type": "轨迹",
        "title": "李建、王强、赵敏行动轨迹",
        "persons": ["lijian001", "wangqiang001", "zhaomin001"],
        "event_time": "2025-10-09",
        "extract_time": "2025-11-25"
    },
    {
        "file": fake_data_dir / "供述笔录_李建.txt",
        "type": "供述",
        "title": "李建供述笔录",
        "persons": ["lijian001"],
        "event_time": "2025-12-10",
        "extract_time": "2025-12-10"
    },
    {
        "file": fake_data_dir / "证人证言_张伟.txt",
        "type": "证言",
        "title": "证人张伟证言笔录",
        "persons": ["zhangwei001"],
        "event_time": "2025-11-20",
        "extract_time": "2025-11-20"
    },
    {
        "file": fake_data_dir / "测谎鉴定报告_李建.txt",
        "type": "鉴定",
        "title": "李建心理测试（测谎）综合报告",
        "persons": ["lijian001"],
        "event_time": "2025-12-08",
        "extract_time": "2025-12-08"
    },
    {
        "file": fake_data_dir / "起诉书_李建案.txt",
        "type": "文书",
        "title": "李建徇私枉法、受贿案起诉书",
        "persons": ["lijian001", "wangqiang001"],
        "event_time": "2026-01-15",
        "extract_time": "2026-01-15"
    },
]

imported_count = 0
failed_count = 0

for evidence in evidence_files:
    file_path = evidence["file"]
    if not file_path.exists():
        print(f"   ✗ 文件不存在: {file_path.name}")
        failed_count += 1
        continue

    manual_info = {
        "evidence_type": evidence["type"],
        "title": evidence["title"],
        "related_persons": evidence["persons"],
        "event_time": evidence["event_time"],
        "extract_time": evidence["extract_time"]
    }

    result = import_evidence(
        file_path=str(file_path),
        case_id=case_id,
        manual_info=manual_info
    )

    if result['success']:
        print(f"   ✓ 已导入: {file_path.name} ({evidence['type']})")
        imported_count += 1
    else:
        print(f"   ✗ 导入失败: {file_path.name} - {result['message']}")
        failed_count += 1

# 5. 统计数据
print("\n5. 数据统计...")
from src.database import get_db_stats

stats = get_db_stats()
print(f"   案件数: {stats['case_count']}")
print(f"   人员数: {stats['person_count']}")
print(f"   证据数: {stats['evidence_count']}")
print(f"   交易记录: {stats['tx_count']}")

conn = get_conn()
chat_count = conn.execute("SELECT COUNT(*) FROM chat_records").fetchone()[0]
call_count = conn.execute("SELECT COUNT(*) FROM call_records").fetchone()[0]
location_count = conn.execute("SELECT COUNT(*) FROM location_records").fetchone()[0]
log_count = conn.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
statement_count = conn.execute("SELECT COUNT(*) FROM statements").fetchone()[0]
doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
conn.close()

print(f"   聊天记录: {chat_count}")
print(f"   通话记录: {call_count}")
print(f"   轨迹记录: {location_count}")
print(f"   系统日志: {log_count}")
print(f"   供述证言: {statement_count}")
print(f"   文书鉴定: {doc_count}")

print(f"\n=== 导入完成 ===")
print(f"成功: {imported_count} 个证据")
print(f"失败: {failed_count} 个证据")
print(f"\n可以启动服务器查看数据：python server.py")
