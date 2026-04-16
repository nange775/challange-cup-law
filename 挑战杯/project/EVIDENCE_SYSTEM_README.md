# 多格式证据导入系统 - 完整文档

## 📋 系统概述

已完成检察侦查平台的证据管理系统升级，实现多格式证据的智能导入和分类存储。

---

## ✅ 已完成的功能

### 1. 数据库结构设计

#### 核心表结构

**案件管理**
- `cases` - 案件基本信息表

**人员管理**
- `persons` - 人员信息表（扩展：新增case_id、role字段）

**证据管理**
- `evidence_meta` - 证据元数据总表（统一入口）
- `person_evidence_relation` - 人-证据关联表（多对多）

**具体证据表**
- `statements` - 供述/辩解/证人证言
- `transactions` - 资金流水（扩展：新增case_id、evidence_id、source_type）
- `chat_records` - 聊天记录
- `documents` - 文书类（判决/鉴定/笔录/测谎）
- `location_records` - 轨迹数据
- `call_records` - 通话记录
- `system_logs` - 系统日志

### 2. 支持的证据类型

| 证据类型 | 存储方式 | 文件格式 | 说明 |
|---------|---------|---------|------|
| **供述/辩解** | 文本表 | PDF/Word/TXT | 存全文+AI提取关键信息 |
| **证人证言** | 文本表 | PDF/Word/TXT | 同上 |
| **资金流水** | 专表 | Excel | 结构化存储，保留精确查询能力 |
| **聊天记录** | 专表 | Excel/TXT | 逐条消息存储 |
| **通话记录** | 专表 | Excel | 主叫/被叫/时长 |
| **轨迹数据** | 专表 | Excel | 时间/经纬度/位置 |
| **系统日志** | 专表 | Excel | 操作/IP/详情 |
| **司法文书** | 文本表 | PDF/Word | 判决书/鉴定意见等 |
| **侦查笔录** | 文本表 | PDF/Word | 各类笔录 |
| **测谎结果** | 文本表 | PDF/Word | 测谎报告 |
| **其他类型** | 文本表 | 任意 | 兜底分类 |

### 3. 智能导入流程

```
用户上传文件
    ↓
【文件解析】自动识别格式（PDF/Word/Excel/TXT）
    ↓
【AI识别】判断证据类型和内容（占位，待集成真实AI）
    ↓
【保存原件】存储到 data/evidence_files/{case_id}/{evidence_id}_filename
    ↓
【创建元数据】在 evidence_meta 表登记
    ↓
【分类存储】根据类型写入对应的专门表
    ├─ 表格类（流水/通话/轨迹/日志）→ 直接存数据库
    └─ 文本类（笔录/证言/文书）→ 存文本+AI提取结构化
    ↓
【自动关联】AI提取人名 → 匹配persons表 → 建立关联关系
    ↓
完成
```

### 4. 核心代码模块

#### `src/database.py` - 数据库操作
- ✅ 完整的表结构定义
- ✅ 案件CRUD操作
- ✅ 证据CRUD操作
- ✅ 人-证据关联管理
- ✅ 各类证据的插入函数

#### `src/evidence_import.py` - 证据导入
- ✅ 多格式文件解析器（PDF/Word/Excel/TXT）
- ✅ AI识别接口（占位实现）
- ✅ 智能字段映射（自动匹配Excel列名）
- ✅ 完整的导入主流程
- ✅ 各类证据的专门导入逻辑

#### `server.py` - API接口
- ✅ POST `/api/cases` - 创建案件
- ✅ GET `/api/cases` - 获取案件列表
- ✅ GET `/api/cases/{case_id}` - 获取案件详情
- ✅ POST `/api/evidence/upload` - 上传证据文件
- ✅ GET `/api/evidence/case/{case_id}` - 获取案件证据
- ✅ GET `/api/evidence/person/{person_id}` - 获取人员证据

---

## 🔧 使用指南

### 后端API调用示例

#### 1. 创建案件
```bash
curl -X POST "http://localhost:8001/api/cases?case_id=CASE001&case_name=测试案件"
```

#### 2. 上传证据（全自动）
```bash
curl -X POST "http://localhost:8001/api/evidence/upload" \
  -F "file=@流水记录.xlsx" \
  -F "case_id=CASE001"
```

#### 3. 上传证据（手动指定类型）
```bash
curl -X POST "http://localhost:8001/api/evidence/upload" \
  -F "file=@笔录.pdf" \
  -F "case_id=CASE001" \
  -F "evidence_type=供述" \
  -F "title=张三供述笔录" \
  -F "related_persons=[\"user001\",\"user002\"]"
```

#### 4. 查看案件证据
```bash
curl "http://localhost:8001/api/evidence/case/CASE001"
```

### Python代码调用示例

```python
from src.database import create_case, get_case_evidences
from src.evidence_import import import_evidence

# 1. 创建案件
create_case("CASE001", "资金诈骗案")

# 2. 导入证据
result = import_evidence(
    file_path="path/to/evidence.xlsx",
    case_id="CASE001",
    manual_info=None  # 全自动识别
)

# 3. 查看证据
evidences = get_case_evidences("CASE001")
print(evidences)
```

---

## 🎯 AI集成点（待实现）

当前AI相关功能已预留接口，需要后续集成：

### 1. 证据类型识别
**位置**: `src/evidence_import.py` → `ai_classify_evidence()`

**输入**:
- 文本内容（PDF/Word提取）
- 表格数据（Excel读取）

**输出**:
```python
{
    'evidence_type': '供述' | '证言' | '流水' | ...,
    'title': '证据标题',
    'event_time': '2024-01-01',
    'extract_time': '2024-02-01', 
    'summary': 'AI生成的摘要',
    'related_persons': [{'name': '张三', 'role': '嫌疑人'}]
}
```

**集成建议**:
- 使用LLM（Claude/GPT/DeepSeek）
- Prompt工程提取关键字段
- 结合规则判断提高准确率

### 2. 人名提取
**位置**: `src/evidence_import.py` → `ai_extract_persons()`

**输入**: 文本内容

**输出**:
```python
[
    {'name': '张三', 'role': '嫌疑人'},
    {'name': '李四', 'role': '证人'}
]
```

**集成建议**:
- NER模型（paddlenlp/LAC）
- 或LLM提取
- 自动匹配数据库中的persons表

### 3. 关键信息提取
**用于**: 供述/证言中提取关键事件、金额、时间

**集成方式**: 扩展 `_import_statement()` 函数

---

## 📊 数据查询示例

### SQL查询

```sql
-- 1. 查看某案件的所有证据
SELECT * FROM evidence_meta WHERE case_id = 'CASE001';

-- 2. 查看某人的所有相关证据
SELECT e.* FROM evidence_meta e
JOIN person_evidence_relation r ON e.evidence_id = r.evidence_id
WHERE r.person_id = 'user001';

-- 3. 查看某案件的资金流水
SELECT * FROM transactions 
WHERE case_id = 'CASE001' 
ORDER BY trade_time;

-- 4. 统计各类证据数量
SELECT evidence_type, COUNT(*) as count
FROM evidence_meta
WHERE case_id = 'CASE001'
GROUP BY evidence_type;

-- 5. 查找涉及特定人物的聊天记录
SELECT * FROM chat_records
WHERE sender_id = 'user001' OR receiver_id = 'user001';
```

### Python查询

```python
from src.database import get_conn
import pandas as pd

conn = get_conn()

# 综合查询：某人的所有证据及详情
query = """
SELECT 
    e.evidence_type,
    e.title,
    e.upload_time,
    COUNT(DISTINCT t.id) as 交易笔数,
    COUNT(DISTINCT c.message_id) as 聊天条数
FROM evidence_meta e
LEFT JOIN person_evidence_relation r ON e.evidence_id = r.evidence_id
LEFT JOIN transactions t ON e.evidence_id = t.evidence_id
LEFT JOIN chat_records c ON e.evidence_id = c.evidence_id
WHERE r.person_id = 'user001'
GROUP BY e.evidence_id
"""

df = pd.read_sql(query, conn)
print(df)
```

---

## 🔄 扩展建议

### 短期扩展（1-2周）

1. **前端页面**
   - 案件管理页面
   - 证据上传页面（拖拽上传）
   - 证据列表展示
   - 证据详情查看

2. **增强功能**
   - 批量上传
   - 上传进度条
   - 错误提示优化

### 中期扩展（2-4周）

1. **AI集成**
   - 接入真实的LLM API
   - 训练/微调专门的证据分类模型
   - NER实体识别

2. **高级功能**
   - 证据时间轴可视化
   - 证据关联图谱
   - 矛盾检测

### 长期扩展（1-2月）

1. **跨证据分析**
   - 笔录 vs 流水交叉验证
   - 聊天记录 vs 通话记录对比
   - 轨迹 vs 时间线重建

2. **智能推理**
   - 自动发现证据链
   - 生成分析报告
   - 辅助侦查建议

---

## ⚠️ 注意事项

### 1. 数据迁移
如有旧数据，直接删除重建：
```bash
cd project
rm -f data/investigation.db
python -c "from src.database import init_db; init_db()"
```

### 2. 外键约束
- 插入交易/聊天/通话记录前，确保相关person存在
- 当前已实现自动创建person，但role默认为"涉案人"

### 3. 文件格式
确保安装依赖：
```bash
pip install pdfplumber python-docx openpyxl pandas
```

### 4. 性能优化
- 大批量导入建议关闭外键检查：
  ```python
  conn.execute("PRAGMA foreign_keys=OFF")
  # 批量插入
  conn.execute("PRAGMA foreign_keys=ON")
  ```

---

## 📝 测试

运行测试脚本：
```bash
cd project
python test_evidence_import.py
```

预期输出：
```
=== 测试证据导入系统 ===

1. 创建测试案件...
   结果: {'success': True, 'case_id': 'CASE001'}

2. 查看案件列表...
   案件数: 1

3. 创建测试数据...
   测试文件: data/test_flow.xlsx

4. 导入证据...
   导入结果: {'success': True, 'evidence_id': '...', 'evidence_type': '流水'}

5. 查看案件证据...
   证据数: 1
   证据列表:
     - 流水: 资金流水记录

6. 查看导入的交易数据...
   交易记录数: 2
   记录详情:
     - 张三: 出 5000.0元 -> 李四
     - 张三: 入 3000.0元 -> 王五

7. 数据库统计...
   {'person_count': 1, 'tx_count': 2, 'case_count': 1, 'evidence_count': 1}

=== 测试完成 ===
```

---

## 📁 文件清单

```
project/
├── src/
│   ├── database.py           ✅ 数据库操作（已完成）
│   ├── evidence_import.py    ✅ 证据导入（已完成，AI占位）
│   ├── ingest.py            （原有财付通导入）
│   ├── anomaly.py           （原有异常检测）
│   ├── graph_analysis.py    （原有图谱分析）
│   ├── profiler.py          （原有人员画像）
│   └── agent.py             （原有AI Agent）
│
├── server.py                 ✅ API接口（已扩展）
├── test_evidence_import.py   ✅ 测试脚本
├── migrate_db.py            （数据迁移工具，已弃用）
└── EVIDENCE_SYSTEM_README.md ✅ 本文档
```

---

## 🚀 下一步工作

### 立即可做
1. ✅ 数据库结构 - **已完成**
2. ✅ 导入逻辑 - **已完成**
3. ✅ API接口 - **已完成**
4. ⏳ 前端界面 - **待开发**

### 需要AI支持
1. ⏳ 证据类型识别
2. ⏳ 人名提取和匹配
3. ⏳ 关键信息提取

### 后续优化
1. ⏳ 批量导入
2. ⏳ 导入历史记录
3. ⏳ 证据删除/修改
4. ⏳ 权限控制

---

## 💡 联系与支持

有问题或建议请联系项目负责人。

**版本**: v2.0.0  
**更新日期**: 2026-04-16  
**状态**: 核心功能完成，AI集成待实现
