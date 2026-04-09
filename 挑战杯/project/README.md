# 检察侦查画像系统

基于财付通资金流水的智能分析平台，提供数据导入、异常检测、关系图谱、人员画像和AI智能侦查功能。

---

## 🎯 系统特性

- ✅ **数据导入**：自动清洗融合财付通交易明细和注册信息
- ✅ **异常检测**：化整为零、深夜交易、财富突增、高频对手方等6大检测算法
- ✅ **关系图谱**：交互式资金流向网络，识别过桥账户和资金回流
- ✅ **人员画像**：综合画像报告，包含风险评级、关系人、侦查建议
- ✅ **AI智能侦查**：大模型对话式分析，自然语言查询

---

## 🏗️ 架构说明

本项目提供**两套完整的用户界面**：

### 1️⃣ Vue.js + FastAPI 版本（前后端分离）✅ **推荐**
- **后端**：FastAPI REST API (`server.py`)
- **前端**：Vue 3 + Element Plus + ECharts
- **端口**：http://localhost:8001
- **优势**：现代化架构，性能优化完善，适合生产部署
- **适用场景**：需要前后端分离的场景

### 2️⃣ Streamlit 版本（一体化）
- **框架**：Streamlit
- **端口**：http://localhost:8501
- **优势**：快速开发，代码简洁
- **适用场景**：原型开发、数据科学项目

---

## 📦 安装依赖

### 方式一：安装所有依赖（推荐）

```bash
cd project
pip install -r requirements.txt
```

### 方式二：按需安装

**仅使用 Vue + FastAPI 版本**：
```bash
pip install fastapi uvicorn pandas openpyxl networkx pyvis anthropic openai
```

**仅使用 Streamlit 版本**：
```bash
pip install streamlit plotly pandas openpyxl networkx pyvis anthropic openai
```

---

## 🚀 快速启动

### 启动 Vue.js + FastAPI 版本（推荐）

#### Windows:
双击运行 `start_server.bat`

或在命令行中：
```bash
cd project
python server.py
```

#### Linux/Mac:
```bash
cd project
python3 server.py
```

**访问地址**：http://localhost:8001

---

### 启动 Streamlit 版本

```bash
cd project
streamlit run app.py
```

**访问地址**：http://localhost:8501

---

## ⚡ 性能优化

### Vue.js + FastAPI 版本优化

**已实现的优化**：
- ✅ 后端内存缓存（5分钟TTL）
- ✅ 前端 Map 缓存
- ✅ 关系图谱节点限制（最多50个）
- ✅ 图表渲染优化
- ✅ 自动缓存清除

**性能提升**：
- 关系图谱：30秒 → 2-5秒（首次）/ <100ms（缓存）**95%+** 🔥
- 月度趋势：10秒 → 1-2秒（首次）/ <100ms（缓存）**98%+** 🔥
- 时段分布：8秒 → 1-2秒（首次）/ <100ms（缓存）**97%+** 🔥

**详细文档**：[FRONTEND_PERFORMANCE_OPTIMIZATION.md](FRONTEND_PERFORMANCE_OPTIMIZATION.md)

---

## 📂 项目结构

```
project/
├── server.py                 # FastAPI 后端主入口
├── app.py                    # Streamlit 主入口
├── start_server.bat          # Windows 快速启动脚本
├── requirements.txt          # Python 依赖
├── config.py                 # 配置文件（LLM配置）
│
├── src/                      # 核心逻辑模块
│   ├── database.py           # SQLite 数据库操作
│   ├── ingest.py             # 数据导入和清洗
│   ├── anomaly.py            # 异常检测算法
│   ├── graph_analysis.py     # 关系图谱分析（已优化）
│   ├── profiler.py           # 人员画像生成
│   └── agent.py              # AI Agent 对话
│
├── pages/                    # Streamlit 页面
│   ├── 1_data_import.py      # 数据导入
│   ├── 2_analysis.py         # 交易分析（已优化）
│   ├── 3_graph.py            # 关系图谱（已优化）
│   ├── 4_profile.py          # 人员画像
│   └── 5_agent.py            # AI 智能侦查
│
├── frontend/                 # Vue.js 前端
│   ├── index.html            # 主页面
│   └── assets/
│       ├── app.js            # Vue 应用逻辑（已优化）
│       └── style.css         # 样式文件
│
├── data/                     # 数据库文件（自动生成）
│   └── investigation.db      # SQLite 数据库
│
└── .streamlit/               # Streamlit 配置
    └── config.toml           # 性能优化配置
```

---

## 🔧 配置说明

### 数据库

系统使用 **SQLite** 数据库，文件位置：`data/investigation.db`

**表结构**：
- `persons` - 人员信息表
- `transactions` - 交易记录表
- `bank_cards` - 银行卡信息表

### LLM 配置

编辑 `config.py` 配置 AI 模型：

```python
LLM_PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": ["claude-3-5-sonnet-20241022", ...],
        "default_model": "claude-3-5-sonnet-20241022"
    },
    "deepseek": {
        "name": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat"],
        "default_model": "deepseek-chat"
    },
    # ...
}
```

**环境变量**：
```bash
# Windows
set ANTHROPIC_API_KEY=your_api_key_here
set DEEPSEEK_API_KEY=your_api_key_here

# Linux/Mac
export ANTHROPIC_API_KEY=your_api_key_here
export DEEPSEEK_API_KEY=your_api_key_here
```

---

## 📊 使用流程

### 1. 数据导入

支持两种导入方式：

#### 手动上传
1. 进入"数据导入"页面
2. 选择 `TenpayTrades.xls`（交易明细）
3. 选择 `TenpayRegInfo1.xls`（注册信息）
4. 点击"导入数据"

#### 自动扫描
1. 将数据文件放在同一目录
2. 输入目录路径
3. 系统自动识别并导入

### 2. 交易分析

1. 选择分析对象
2. 点击"执行查询"
3. 查看：
   - 资金流水概况
   - 月度趋势图
   - 交易时段分布
   - 异常检测结果

### 3. 关系图谱

1. 选择分析对象
2. 点击"执行查询"
3. 查看：
   - 网络指标（度数、入度、出度）
   - 交互式图谱（可拖拽、缩放）
   - 疑似过桥账户
   - 资金回流环路

### 4. 人员画像

1. 选择分析对象
2. 点击"生成画像"
3. 查看完整画像报告
4. 下载 TXT 格式报告

### 5. AI 智能侦查

1. 配置 LLM API Key
2. 输入自然语言查询
3. AI 自动调用工具分析
4. 获取结构化答案

---

## 🧪 测试数据

系统支持财付通数据格式：

**TenpayTrades.xls 字段**：
- 交易时间、交易类型、交易对方、交易对方账号
- 商品名称、收/支、金额、当前状态、交易单号等

**TenpayRegInfo1.xls 字段**：
- 微信昵称、身份证号、真实姓名、账号、性别、注册时间等

---

## 🐛 故障排查

### 问题1：导入失败

**症状**：提示"文件格式错误"或"字段缺失"

**解决方案**：
1. 检查文件是否为 `.xls` 或 `.xlsx` 格式
2. 确认文件包含必需的字段
3. 查看终端/日志中的详细错误信息

### 问题2：图谱加载慢

**症状**：超过10秒未加载完成

**解决方案**：
1. 检查浏览器控制台是否有错误
2. 减少 `max_nodes` 参数（`server.py` 第220行）
3. 查看 [FRONTEND_PERFORMANCE_OPTIMIZATION.md](FRONTEND_PERFORMANCE_OPTIMIZATION.md)

### 问题3：AI 智能侦查报错

**症状**：提示 API Key 错误

**解决方案**：
1. 确认已设置环境变量或在界面输入 API Key
2. 检查网络连接
3. 查看 API Key 是否有效

---

## 📝 开发说明

### 添加新的异常检测算法

编辑 `src/anomaly.py`：

```python
def detect_new_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """新的异常检测算法"""
    # 实现检测逻辑
    return result_df

def run_all_detections(df: pd.DataFrame) -> dict:
    results = {
        # ...
        "new_pattern": detect_new_pattern(df),
    }
    return results
```

### 添加新的图谱算法

编辑 `src/graph_analysis.py`：

```python
def new_graph_algorithm(G: nx.DiGraph, target: str) -> list:
    """新的图谱分析算法"""
    # 实现算法逻辑
    return results
```

---

## 🔐 安全说明

⚠️ **重要提示**：

1. 本系统仅供辅助侦查工作使用，分析结果需结合实际情况核实
2. 数据库文件包含敏感信息，请妥善保管
3. 生产环境建议：
   - 使用 HTTPS
   - 配置防火墙
   - 启用用户认证
   - 使用 PostgreSQL 替代 SQLite
   - 使用 Redis 替代内存缓存

---

## 📄 许可证

本项目仅供学习和研究使用。

---

## 📮 联系方式

如有问题或建议，请联系项目负责人。

---

**更新日期**：2026-04-09  
**版本**：v1.0.0 - 性能优化版
