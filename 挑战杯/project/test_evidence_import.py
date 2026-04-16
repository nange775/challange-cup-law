"""测试证据导入功能"""
import pandas as pd
from pathlib import Path
from src.database import create_case, get_all_cases, get_case_evidences, get_conn
from src.evidence_import import import_evidence

print("=== 测试证据导入系统 ===\n")

# 1. 创建测试案件
print("1. 创建测试案件...")
result = create_case("CASE001", "测试案件-资金诈骗案")
print(f"   结果: {result}")

# 2. 查看案件列表
print("\n2. 查看案件列表...")
cases = get_all_cases()
print(f"   案件数: {len(cases)}")
if not cases.empty:
    print(f"   案件: {cases.to_dict('records')}")

# 3. 创建测试Excel文件（模拟资金流水）
print("\n3. 创建测试数据...")
test_data = pd.DataFrame([
    {"账号": "user001", "姓名": "张三", "交易时间": "2024-01-01 10:00:00",
     "金额": 5000, "对方": "李四", "收支": "出", "用途": "转账"},
    {"账号": "user001", "姓名": "张三", "交易时间": "2024-01-02 15:30:00",
     "金额": 3000, "对方": "王五", "收支": "入", "用途": "收款"},
])

test_file = Path("data/test_flow.xlsx")
test_file.parent.mkdir(exist_ok=True)
test_data.to_excel(test_file, index=False)
print(f"   测试文件: {test_file}")

# 4. 导入证据
print("\n4. 导入证据...")
result = import_evidence(
    file_path=str(test_file),
    case_id="CASE001",
    manual_info=None  # 全自动识别
)
print(f"   导入结果: {result}")

# 5. 查看证据列表
print("\n5. 查看案件证据...")
evidences = get_case_evidences("CASE001")
print(f"   证据数: {len(evidences)}")
if not evidences.empty:
    print(f"   证据列表:")
    for idx, row in evidences.iterrows():
        print(f"     - {row['evidence_type']}: {row['title']}")

# 6. 查看导入的交易数据
print("\n6. 查看导入的交易数据...")
conn = get_conn()
transactions = pd.read_sql("SELECT * FROM transactions WHERE case_id = 'CASE001'", conn)
conn.close()
print(f"   交易记录数: {len(transactions)}")
if not transactions.empty:
    print(f"   记录详情:")
    for idx, row in transactions.iterrows():
        print(f"     - {row['user_name']}: {row['direction']} {row['amount']/100}元 -> {row['counterpart_name']}")

# 7. 测试数据库统计
print("\n7. 数据库统计...")
from src.database import get_db_stats
stats = get_db_stats()
print(f"   {stats}")

print("\n=== 测试完成 ===")
