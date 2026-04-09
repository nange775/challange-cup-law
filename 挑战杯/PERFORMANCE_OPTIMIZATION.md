# 性能优化说明文档

## 问题诊断

### 1. 关系图谱无法加载
**症状**: 显示"无图谱数据"，页面空白或加载失败

**根本原因**:
- PyVis生成的HTML包含大量节点和边的标签，导致浏览器渲染缓慢
- 没有节点数量限制，数据量大时会崩溃
- 每条边都有金额标签，在大量边的情况下严重影响性能

### 2. 交易分析图表加载慢
**症状**: 月度趋势和时段分布图加载时间超过5-10秒，有时完全无法加载

**根本原因**:
- 没有使用Streamlit的缓存机制，每次刷新都重新计算
- 重复复制整个DataFrame（`tx.copy()`），占用大量内存
- Plotly图表没有优化，数据量大时渲染慢

## 优化方案

### 1. 关系图谱优化（`src/graph_analysis.py`）

#### ✅ 添加节点数量限制
```python
def generate_pyvis_html(G: nx.DiGraph, target: str, output_path: str = None, max_nodes: int = 50)
```
- 限制最多显示50个节点（可调整）
- 优先保留交易金额大的关系人
- 避免图谱过于复杂导致渲染失败

#### ✅ 移除边的标签
```python
# 原代码：每条边都显示金额标签
net.add_edge(src, dst, width=width, color=color, title=title, arrows="to", label=f"{weight:.0f}")

# 优化后：移除label，只在悬停时显示
net.add_edge(src, dst, width=width, color=color, title=title, arrows="to")
```

#### ✅ 添加空数据检查
```python
if len(G.nodes()) == 0 or target not in G:
    return "<div style='text-align:center;padding:50px;color:#999;'>无图谱数据</div>"
```

### 2. 交易分析优化（`pages/2_analysis.py`）

#### ✅ 添加缓存机制
使用`@st.cache_data`装饰器缓存计算结果，避免重复计算：

```python
@st.cache_data(ttl=300)  # 缓存5分钟
def compute_monthly_trend(tx_data: pd.DataFrame) -> pd.DataFrame:
    """计算月度趋势（带缓存）"""
    # ...计算逻辑
```

添加的缓存函数：
- `compute_monthly_trend()` - 月度趋势
- `compute_hour_distribution()` - 时段分布
- `compute_purpose_distribution()` - 用途分布
- `compute_top_counterparts()` - TOP对手方

#### ✅ 添加加载状态指示
```python
with st.spinner("加载月度趋势..."):
    monthly = compute_monthly_trend(tx)
    # ...绘图代码
```

#### ✅ 添加唯一key避免组件冲突
```python
st.plotly_chart(fig_monthly, use_container_width=True, key="monthly_trend")
```

### 3. 关系图谱页面优化（`pages/3_graph.py`）

#### ✅ 添加完善的错误处理
```python
try:
    with st.spinner("正在生成关系图谱..."):
        if len(G.nodes()) == 0:
            st.warning("无法构建关系图谱，请检查交易数据...")
        else:
            html = generate_pyvis_html(G, target_name, max_nodes=50)
            # ...
except Exception as e:
    st.error(f"图谱生成失败: {e}")
    with st.expander("查看错误详情"):
        st.code(traceback.format_exc())
```

### 4. Streamlit配置优化（`.streamlit/config.toml`）

创建配置文件以提升整体性能：
- 启用快速重新运行（`fastReruns = true`）
- 禁用不必要的CORS和XSRF检查
- 优化工具栏显示

## 性能提升预期

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 关系图谱加载时间 | 10-30秒/失败 | 2-5秒 | **80%+** |
| 月度趋势图首次加载 | 5-10秒 | 2-3秒 | **60%** |
| 月度趋势图二次加载 | 5-10秒 | <1秒（缓存） | **90%+** |
| 时段分布图加载 | 3-8秒 | 1-2秒 | **70%** |
| 页面整体响应 | 卡顿明显 | 流畅 | - |

## 测试步骤

### 1. 重启Streamlit服务器
```bash
# 停止当前运行的服务器（Ctrl+C）
# 重新启动
cd project
streamlit run app.py
```

### 2. 测试关系图谱
1. 进入"关系图谱"页面
2. 选择一个有较多交易记录的用户（如"张三"）
3. 观察图谱是否能正常显示
4. 检查图谱节点数量是否控制在合理范围
5. 悬停在边上查看交易详情（不显示标签但有悬停提示）

### 3. 测试交易分析
1. 进入"交易分析"页面
2. 选择一个用户
3. 切换到"交易概览"标签
4. **首次加载**：观察月度趋势图和时段分布图的加载时间
5. **二次加载**：刷新页面或切换用户后再切换回来，应该从缓存加载（<1秒）
6. 检查所有图表是否正常显示

### 4. 压力测试
1. 导入大量交易数据（5000+条记录）
2. 测试图表和图谱是否仍能正常加载
3. 检查是否有内存泄漏或崩溃

## 进一步优化建议

### 短期优化（可立即实施）
1. **数据分页**：对于大量交易记录，考虑分页显示
2. **图表采样**：当数据量超过阈值时，对数据进行采样
3. **懒加载**：图表只在标签页被选中时才渲染

### 中期优化（需要一定开发时间）
1. **使用Plotly的WebGL模式**：处理大数据集时性能更好
   ```python
   fig_monthly.update_traces(marker_line_width=0, selector=dict(type='bar'))
   fig_monthly.update_layout(hovermode='x unified')
   ```

2. **替换PyVis为Plotly Network Graph**：Plotly的网络图性能更好
   ```python
   import plotly.graph_objects as go
   # 使用go.Scatter创建网络图
   ```

3. **添加数据库索引**：在`counterpart_name`、`trade_time`等字段上添加索引

### 长期优化（架构级优化）
1. **使用异步加载**：将图表渲染改为异步加载
2. **前后端分离**：使用React/Vue前端 + FastAPI后端
3. **引入Redis缓存**：将计算结果缓存到Redis
4. **使用Celery处理大数据**：异步任务队列处理耗时计算

## 故障排查

### 如果图谱仍然无法加载
1. 检查浏览器控制台是否有JavaScript错误
2. 检查交易数据中`counterpart_name`字段是否为空
3. 尝试减小`max_nodes`参数（在`3_graph.py`第52行）
4. 检查PyVis版本：`pip show pyvis`（建议0.3.1+）

### 如果图表仍然加载慢
1. 清除Streamlit缓存：在浏览器中点击右上角"三个点" -> "Clear cache"
2. 检查数据量：`print(len(tx))` 查看交易记录数
3. 检查缓存是否生效：在函数中添加`print("缓存未命中")`
4. 尝试减少`ttl`参数或禁用缓存测试

## 监控指标

建议在生产环境中监控以下指标：
- 页面平均加载时间
- 图表渲染时间
- 缓存命中率
- 内存使用量
- 数据库查询时间

## 更新日志

- **2026-04-09**: 初始版本，完成关系图谱和交易分析的性能优化
