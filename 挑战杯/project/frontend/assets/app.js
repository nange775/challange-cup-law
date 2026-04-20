const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;
const API = '/api';

const app = createApp({
    setup() {
        // ==================== 全局状态 ====================
        const isLoading = ref(true);  // 全局加载状态
        const currentPage = ref('home');
        const currentCaseId = ref('');  // 当前选中的案件ID
        const stats = ref({});
        const persons = ref([]);
        const selectedUser = ref('');
        const cases = ref([]);  // 案件列表

        const navItems = [
            { page: 'home', icon: '\u{1F3E0}', label: '首页' },
            { page: 'import', icon: '\u{1F4E5}', label: '数据导入' },
            { page: 'analysis', icon: '\u{1F4CA}', label: '交易分析' },
            { page: 'graph', icon: '\u{1F578}', label: '关系图谱' },
            { page: 'profile', icon: '\u{1F464}', label: '人员画像' },
            { page: 'agent', icon: '\u{1F916}', label: 'AI 智能侦查' },
            { page: 'help', icon: '\u{1F4AC}', label: '系统说明' },
        ];

        const homeCards = [
            { page: 'import', icon: '\u{1F4E5}', title: '数据导入', desc: '支持多格式文件导入，包括财付通数据、Excel、PDF、Word及图片OCR，系统自动识别格式、提取信息并录入。' },
            { page: 'analysis', icon: '\u{1F4CA}', title: '交易分析', desc: '六大异常检测算法: 化整为零、深夜交易、财富突增等。' },
            { page: 'graph', icon: '\u{1F578}', title: '关系图谱', desc: '交互式资金流向网络, 识别过桥账户和资金回流。' },
            { page: 'profile', icon: '\u{1F464}', title: '人员画像', desc: '综合画像报告: 风险评级、关系人、侦查建议。' },
            { page: 'agent', icon: '\u{1F916}', title: 'AI 智能侦查', desc: '大模型对话式分析, 自然语言查询, 自动调用工具。' },
            { page: 'help', icon: '\u2139', title: '系统说明', desc: '前后端分离架构, FastAPI后端 + Vue3前端。' },
        ];

        // ==================== 数据加载 ====================
        let isInitialLoad = true;  // 首次加载标志

        async function loadStats() {
            try {
                // 只加载案件列表，延迟加载其他数据
                const res = await axios.get(`${API}/cases`);
                cases.value = res.data;

                // 如果有案件但未选中，自动选中第一个
                if (cases.value.length > 0 && !currentCaseId.value) {
                    currentCaseId.value = cases.value[0].case_id;

                    // 首次加载时延迟加载案件数据，避免阻塞页面渲染
                    if (isInitialLoad) {
                        isInitialLoad = false;
                        setTimeout(() => loadCaseData(), 100);
                    } else {
                        await loadCaseData();
                    }
                } else if (currentCaseId.value) {
                    await loadCaseData();
                }
            } catch (e) {
                console.error('加载案件列表失败:', e);
            }
        }

        async function loadCaseData() {
            if (!currentCaseId.value) {
                stats.value = {};
                persons.value = [];
                return;
            }

            try {
                // 先快速加载统计，再加载人员列表
                const statsPromise = axios.get(`${API}/stats?case_id=${currentCaseId.value}`);

                // 统计数据优先显示
                const s = await statsPromise;
                stats.value = s.data;

                // 人员列表可以稍后加载
                const p = await axios.get(`${API}/persons?case_id=${currentCaseId.value}`);
                persons.value = p.data;
            } catch (e) {
                console.error('加载案件数据失败:', e);
            }
        }

        function onCaseChange() {
            // 切换案件时重新加载数据并清除缓存
            loadCaseData();
            analysisCache.clear();
            graphCache.clear();
            selectedUser.value = '';
            analysisData.value = null;
            graphData.value = null;
            profileData.value = null;
        }

        // ==================== 数据导入 ====================
        const importTab = ref('upload');
        const uploadFiles = reactive({ trades: null, reg: null });
        const uploading = ref(false);
        const scanDir = ref('');
        const scanning = ref(false);

        // ==================== 证据导入 ====================
        const evidenceFiles = ref([]);
        const evidenceFileList = ref([]);
        const evidenceType = ref('auto');
        const evidenceDesc = ref('');
        const evidenceUploading = ref(false);
        const evidenceResults = ref([]);

        // 新建案件
        const showCreateCaseDialog = ref(false);
        const newCaseId = ref('');
        const newCaseName = ref('');
        const creatingCase = ref(false);

        // 财付通文件配对验证状态
        const tenpayValidation = reactive({
            hasTrades: false,
            hasRegInfo: false,
            isValid: false
        });

        // 检查财付通文件配对
        function checkTenpayPair() {
            const files = evidenceFiles.value;
            const hasTrades = files.some(f =>
                f.name.toLowerCase().includes('tenpaytrades') ||
                f.name.toLowerCase().includes('trades')
            );
            const hasRegInfo = files.some(f =>
                f.name.toLowerCase().includes('tenpayreginfo') ||
                f.name.toLowerCase().includes('reginfo')
            );

            tenpayValidation.hasTrades = hasTrades;
            tenpayValidation.hasRegInfo = hasRegInfo;
            tenpayValidation.isValid = (hasTrades && hasRegInfo) || (!hasTrades && !hasRegInfo);

            // 如果检测到财付通文件但配对不正确，显示警告
            if (hasTrades && !hasRegInfo) {
                ElementPlus.ElMessage.warning('检测到交易明细文件，还需导入对应的注册信息文件(TenpayRegInfo1.xls)');
            } else if (!hasTrades && hasRegInfo) {
                ElementPlus.ElMessage.warning('检测到注册信息文件，还需导入对应的交易明细文件(TenpayTrades.xls)');
            }
        }

        async function doUpload() {
            uploading.value = true;
            try {
                const form = new FormData();
                form.append('trades', uploadFiles.trades);
                form.append('reginfo', uploadFiles.reg);
                const res = await axios.post(`${API}/upload`, form);
                ElementPlus.ElMessage.success(`导入成功: ${res.data.name}(${res.data.user_id}), ${res.data.tx_count}笔交易`);
                uploadFiles.trades = null;
                uploadFiles.reg = null;
                // 清除前端缓存
                analysisCache.clear();
                graphCache.clear();
                relationCache.clear();
                await loadStats();
            } catch (e) {
                ElementPlus.ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message));
            }
            uploading.value = false;
        }

        async function doScan() {
            if (!scanDir.value) return;
            scanning.value = true;
            try {
                const res = await axios.post(`${API}/auto-import?directory=${encodeURIComponent(scanDir.value)}`);
                const results = res.data;
                let ok = 0, fail = 0;
                results.forEach(r => {
                    if (r.error) { fail++; ElementPlus.ElMessage.error(r.error); }
                    else { ok++; ElementPlus.ElMessage.success(`导入: ${r.name}(${r.user_id}), ${r.tx_count}笔`); }
                });
                if (ok > 0) {
                    // 清除前端缓存
                    analysisCache.clear();
                    graphCache.clear();
                    relationCache.clear();
                    await loadStats();
                }
            } catch (e) {
                ElementPlus.ElMessage.error('扫描失败: ' + e.message);
            }
            scanning.value = false;
        }
        async function doClear() {
            try {
                await axios.post(`${API}/clear`);
                ElementPlus.ElMessage.success('已清空所有数据');
                // 清除前端缓存
                analysisCache.clear();
                graphCache.clear();
                relationCache.clear();
                await loadStats();
            } catch (e) {
                ElementPlus.ElMessage.error('清空失败: ' + e.message);
            }
        }

        async function doCreateCase() {
            if (!newCaseId.value || !newCaseName.value) {
                ElementPlus.ElMessage.warning('请填写完整案件信息');
                return;
            }

            creatingCase.value = true;
            try {
                const res = await axios.post(`${API}/cases?case_id=${encodeURIComponent(newCaseId.value)}&case_name=${encodeURIComponent(newCaseName.value)}`);
                if (res.data.success) {
                    ElementPlus.ElMessage.success('案件创建成功');
                    // 刷新案件列表
                    await loadStats();
                    // 自动选中新建的案件
                    currentCaseId.value = newCaseId.value;
                    // 关闭对话框
                    showCreateCaseDialog.value = false;
                    newCaseId.value = '';
                    newCaseName.value = '';
                } else {
                    ElementPlus.ElMessage.error(res.data.error || '创建失败');
                }
            } catch (e) {
                ElementPlus.ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message));
            }
            creatingCase.value = false;
        }

        async function doEvidenceUpload() {
            if (!currentCaseId.value) {
                ElementPlus.ElMessage.warning('请先选择或创建案件');
                return;
            }

            if (evidenceFiles.value.length === 0) {
                ElementPlus.ElMessage.warning('请选择要导入的文件');
                return;
            }

            // 财付通文件配对检测
            const hasTrades = evidenceFiles.value.some(f =>
                f.name.toLowerCase().includes('tenpaytrades') ||
                f.name.toLowerCase().includes('trades')
            );
            const hasRegInfo = evidenceFiles.value.some(f =>
                f.name.toLowerCase().includes('tenpayreginfo') ||
                f.name.toLowerCase().includes('reginfo')
            );

            if (hasTrades && !hasRegInfo) {
                ElementPlus.ElMessage.warning('检测到交易明细文件，还需导入对应的注册信息文件(TenpayRegInfo1.xls)');
                return;
            }
            if (!hasTrades && hasRegInfo) {
                ElementPlus.ElMessage.warning('检测到注册信息文件，还需导入对应的交易明细文件(TenpayTrades.xls)');
                return;
            }

            evidenceUploading.value = true;
            evidenceResults.value = [];

            const results = [];
            for (const file of evidenceFiles.value) {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('case_id', currentCaseId.value);
                formData.append('evidence_type', evidenceType.value === 'auto' ? '' : evidenceType.value);
                formData.append('description', evidenceDesc.value || '自动导入');

                try {
                    const res = await axios.post(`${API}/evidence/upload`, formData);
                    results.push({
                        filename: file.name,
                        status: res.data.status || 'success',
                        evidence_type: res.data.evidence_type || evidenceType.value,
                        entities: res.data.entities || null
                    });
                    ElementPlus.ElMessage.success(`导入成功: ${file.name}`);
                } catch (e) {
                    results.push({
                        filename: file.name,
                        status: 'error',
                        error: e.response?.data?.detail || e.message
                    });
                    ElementPlus.ElMessage.error(`导入失败: ${file.name} - ${e.response?.data?.detail || e.message}`);
                }
            }

            evidenceResults.value = results;
            evidenceUploading.value = false;

            // 清空文件列表并刷新统计
            evidenceFiles.value = [];
            evidenceFileList.value = [];

            // 清除前端缓存并重新加载当前案件数据
            analysisCache.clear();
            graphCache.clear();
            await loadCaseData();
        }

        // ==================== 交易分析 ====================
        const analysisData = ref(null);
        const anomalyData = ref(null);
        const counterparts = ref([]);
        const monthlyData = ref([]);
        const hourData = ref([]);
        const chartMonthly = ref(null);
        const chartHour = ref(null);
        const chartCounterpart = ref(null);
        const analysisLoading = ref(false);
        const activeAnalysisTab = ref('overview'); // 默认显示"交易概览"
        const analysisCache = new Map(); // 前端缓存

        const analysisSummary = computed(() => {
            if (!analysisData.value) return {};
            const tx = analysisData.value;
            return {
                totalCount: tx.length,
                totalIncome: tx.filter(t => t.direction === '入').reduce((s, t) => s + t.amount_yuan, 0),
                totalExpense: tx.filter(t => t.direction === '出').reduce((s, t) => s + t.amount_yuan, 0),
            };
        });

        async function loadAnalysis() {
            if (!selectedUser.value) {
                ElementPlus.ElMessage.warning('请先选择分析对象');
                return;
            }
            const uid = selectedUser.value;

            // 检查缓存
            if (analysisCache.has(uid)) {
                console.log('使用缓存数据:', uid);
                const cached = analysisCache.get(uid);
                analysisData.value = cached.tx;
                anomalyData.value = cached.anomaly;
                counterparts.value = cached.counterparts;
                monthlyData.value = cached.monthly;
                hourData.value = cached.hour;
                // 等待DOM更新后渲染所有图表
                await nextTick();
                setTimeout(() => {
                    renderMonthlyChart();
                    renderHourChart();
                    renderCounterpartChart();
                }, 100);
                return;
            }

            console.log('加载新数据:', uid);
            analysisLoading.value = true;
            try {
                const [txRes, anomRes, cpRes, monthRes, hourRes] = await Promise.all([
                    axios.get(`${API}/transactions/${uid}?limit=9999`),
                    axios.get(`${API}/anomaly/${uid}`),
                    axios.get(`${API}/counterparts/${uid}?top_n=20`),
                    axios.get(`${API}/monthly/${uid}`),
                    axios.get(`${API}/hour-distribution/${uid}`),
                ]);

                console.log('数据加载完成:', {
                    tx: txRes.data.length,
                    monthly: monthRes.data.length,
                    hour: hourRes.data.length
                });

                analysisData.value = txRes.data;
                anomalyData.value = anomRes.data;
                counterparts.value = cpRes.data;
                monthlyData.value = monthRes.data;
                hourData.value = hourRes.data;

                // 保存到缓存
                analysisCache.set(uid, {
                    tx: txRes.data,
                    anomaly: anomRes.data,
                    counterparts: cpRes.data,
                    monthly: monthRes.data,
                    hour: hourRes.data,
                });

                // 等待DOM更新后渲染所有图表（都在"交易概览"标签内）
                await nextTick();
                setTimeout(() => {
                    renderMonthlyChart();
                    renderHourChart();
                    renderCounterpartChart();
                }, 100);
            } catch (e) {
                console.error('加载失败:', e);
                ElementPlus.ElMessage.error('分析失败: ' + e.message);
            }
            analysisLoading.value = false;
        }

        function onAnalysisTabChange(tabName) {
            activeAnalysisTab.value = tabName;
            // 切换到"交易概览"时渲染所有图表
            if (tabName === 'overview') {
                nextTick(() => {
                    setTimeout(() => {
                        renderMonthlyChart();
                        renderHourChart();
                        renderCounterpartChart();
                    }, 50);
                });
            }
        }

        function renderMonthlyChart() {
            if (!chartMonthly.value || !monthlyData.value.length) return;

            // 等待容器渲染完成
            setTimeout(() => {
                if (!chartMonthly.value) return;

                let chart = echarts.getInstanceByDom(chartMonthly.value);
                if (!chart) chart = echarts.init(chartMonthly.value);

                const months = monthlyData.value.map(d => d.month);
                chart.setOption({
                    tooltip: { trigger: 'axis' },
                    legend: { data: ['入账', '出账'] },
                    xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
                    yAxis: { type: 'value', name: '金额(元)' },
                    series: [
                        { name: '入账', type: 'bar', data: monthlyData.value.map(d => d.income), itemStyle: { color: '#67c23a' } },
                        { name: '出账', type: 'bar', data: monthlyData.value.map(d => d.expense), itemStyle: { color: '#f56c6c' } },
                    ],
                    grid: { bottom: 80 },
                    animation: true,
                    animationDuration: 800,
                });

                // 强制调整大小
                chart.resize();
                console.log('月度图表已渲染');
            }, 100);
        }

        function renderHourChart() {
            if (!chartHour.value || !hourData.value.length) return;

            // 等待容器渲染完成
            setTimeout(() => {
                if (!chartHour.value) return;

                let chart = echarts.getInstanceByDom(chartHour.value);
                if (!chart) chart = echarts.init(chartHour.value);

                chart.setOption({
                    tooltip: { trigger: 'axis' },
                    xAxis: { type: 'category', data: hourData.value.map(d => d.hour + '时'), name: '时段' },
                    yAxis: { type: 'value', name: '交易笔数' },
                    series: [{
                        type: 'bar',
                        data: hourData.value.map(d => ({
                            value: d.count,
                            itemStyle: { color: d.hour >= 0 && d.hour < 6 ? '#f56c6c' : '#409eff' }
                        })),
                    }],
                    animation: true,
                    animationDuration: 800,
                    markArea: {
                        silent: true,
                        data: [[
                            { xAxis: '0时', itemStyle: { color: 'rgba(245, 108, 108, 0.1)' } },
                            { xAxis: '5时' }
                        ]],
                        label: { show: true, position: 'top', formatter: '深夜时段' }
                    }
                });

                // 强制调整大小
                chart.resize();
                console.log('时段图表已渲染');
            }, 100);
        }

        function renderCounterpartChart() {
            if (!chartCounterpart.value || !counterparts.value.length) return;

            // 等待容器渲染完成
            setTimeout(() => {
                if (!chartCounterpart.value) return;

                let chart = echarts.getInstanceByDom(chartCounterpart.value);
                if (!chart) chart = echarts.init(chartCounterpart.value);

                const top10 = counterparts.value.slice(0, 10);
                const names = top10.map(d => d.counterpart_name);
                const incomeData = top10.map(d => d.total_in_yuan || 0);
                const expenseData = top10.map(d => d.total_out_yuan || 0);

                chart.setOption({
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: { type: 'shadow' }
                    },
                    legend: { data: ['入账', '出账'] },
                    xAxis: {
                        type: 'category',
                        data: names,
                        axisLabel: {
                            rotate: 45,
                            interval: 0,
                            fontSize: 11
                        }
                    },
                    yAxis: { type: 'value', name: '金额(元)' },
                    series: [
                        {
                            name: '入账',
                            type: 'bar',
                            data: incomeData,
                            itemStyle: { color: '#67c23a' }
                        },
                        {
                            name: '出账',
                            type: 'bar',
                            data: expenseData,
                            itemStyle: { color: '#f56c6c' }
                        },
                    ],
                    grid: { bottom: 100, left: 60, right: 40 },
                    animation: true,
                    animationDuration: 800,
                });

                // 强制调整大小
                chart.resize();
                console.log('对手方图表已渲染');
            }, 100);
        }

        // ==================== 关系图谱 ====================
        const graphData = ref(null);
        const graphLoading = ref(false);
        const graphIframeSrc = ref('');
        const relationTargetUser = ref('');
        const relationshipData = ref(null);
        const relationshipLoading = ref(false);
        const relationshipIframeSrc = ref('');
        const relationCache = new Map();
        const graphCache = new Map(); // 图谱缓存

        // 将 HTML 字符串转为 Blob URL 供 iframe 加载，避免 srcdoc CSP 限制
        function setGraphIframe(html) {
            // 释放旧的 Blob URL
            if (graphIframeSrc.value && graphIframeSrc.value.startsWith('blob:')) {
                URL.revokeObjectURL(graphIframeSrc.value);
            }
            if (!html) {
                graphIframeSrc.value = '';
                return;
            }
            const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
            graphIframeSrc.value = URL.createObjectURL(blob);
        }

        function setRelationshipIframe(html) {
            if (relationshipIframeSrc.value && relationshipIframeSrc.value.startsWith('blob:')) {
                URL.revokeObjectURL(relationshipIframeSrc.value);
            }
            if (!html) {
                relationshipIframeSrc.value = '';
                return;
            }
            const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
            relationshipIframeSrc.value = URL.createObjectURL(blob);
        }

        async function loadGraph() {
            if (!selectedUser.value) {
                ElementPlus.ElMessage.warning('请先选择分析对象');
                return;
            }

            const uid = selectedUser.value;

            // 检查缓存
            if (graphCache.has(uid)) {
                const cached = graphCache.get(uid);
                graphData.value = cached;
                await nextTick();
                setGraphIframe(cached.graph_html || '');
                return;
            }

            graphLoading.value = true;
            graphData.value = null;
            graphIframeSrc.value = '';
            try {
                const res = await axios.get(`${API}/graph/${uid}`);
                graphData.value = res.data;

                // 保存到缓存
                graphCache.set(uid, res.data);

                await nextTick();
                setGraphIframe(res.data.graph_html || '');
            } catch (e) {
                ElementPlus.ElMessage.error('图谱加载失败: ' + e.message);
                console.error(e);
            }
            graphLoading.value = false;
        }

        async function analyzeRelationship() {
            if (!selectedUser.value || !relationTargetUser.value) {
                ElementPlus.ElMessage.warning('请选择两个待分析的节点');
                return;
            }
            if (selectedUser.value === relationTargetUser.value) {
                ElementPlus.ElMessage.warning('请选择两个不同的节点');
                return;
            }

            const cacheKey = [selectedUser.value, relationTargetUser.value].sort().join('__');
            if (relationCache.has(cacheKey)) {
                relationshipData.value = relationCache.get(cacheKey);
                await nextTick();
                setRelationshipIframe(relationshipData.value.relationship_graph_html || '');
                return;
            }

            relationshipLoading.value = true;
            relationshipData.value = null;
            relationshipIframeSrc.value = '';
            try {
                const res = await axios.get(`${API}/relationship`, {
                    params: {
                        user_a: selectedUser.value,
                        user_b: relationTargetUser.value,
                    },
                });
                relationshipData.value = res.data;
                relationCache.set(cacheKey, res.data);
                await nextTick();
                setRelationshipIframe(res.data.relationship_graph_html || '');
            } catch (e) {
                ElementPlus.ElMessage.error('双节点关系分析失败: ' + (e.response?.data?.detail || e.message));
                console.error(e);
            }
            relationshipLoading.value = false;
        }

        // ==================== 人员画像 ====================
        const profileData = ref(null);
        const profileLoading = ref(false);
        const profileExpanded = ref(['info', 'risk', 'contacts']);

        async function loadProfile() {
            if (!selectedUser.value) return;
            profileLoading.value = true;
            try {
                const res = await axios.get(`${API}/profile/${selectedUser.value}`);
                profileData.value = res.data;
            } catch (e) { console.error(e); }
            profileLoading.value = false;
        }

        function downloadReport() {
            if (!profileData.value?.report_text) return;
            const blob = new Blob([profileData.value.report_text], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `画像报告_${profileData.value.person?.name || 'unknown'}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        }

        // ==================== AI Agent ====================
        const chatMessages = ref([]);
        const chatHistory = ref([]);
        const chatInput = ref('');
        const chatLoading = ref(false);
        const chatBox = ref(null);
        const providers = ref({});
        const showApiKey = ref(false);
        const agentConfig = reactive({
            provider: 'deepseek',
            model: 'deepseek-chat',
            apiKey: '',
            baseUrl: '',
        });
        const currentProviderModels = computed(() => {
            return providers.value[agentConfig.provider]?.models || [];
        });
        const sampleQuestions = [
            '帮我分析李四的资金异常情况',
            '李四与宗正貌之间有哪些交易?',
            '生成李四的完整画像报告',
            '李四在2023年3-5月有什么异常?',
            '哪些月份李四的入账金额异常高?',
        ];

        async function loadProviders() {
            try {
                const res = await axios.get(`${API}/providers`);
                providers.value = res.data;
            } catch (e) { console.error(e); }
        }

        function onProviderChange() {
            const p = providers.value[agentConfig.provider];
            if (p) agentConfig.model = p.default_model || '';
        }

        function renderMd(text) {
            try { return marked.parse(text || ''); }
            catch { return text; }
        }

        async function sendChat() {
            const msg = chatInput.value.trim();
            if (!msg || chatLoading.value) return;
            chatMessages.value.push({ role: 'user', content: msg });
            chatInput.value = '';
            chatLoading.value = true;
            await nextTick();
            if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;

            try {
                const apiMessages = [...chatHistory.value, { role: 'user', content: msg }];
                const res = await axios.post(`${API}/chat`, {
                    messages: apiMessages,
                    provider_id: agentConfig.provider,
                    api_key: agentConfig.apiKey,
                    model: agentConfig.model,
                    base_url: agentConfig.baseUrl,
                });
                const reply = res.data.reply;
                chatMessages.value.push({ role: 'assistant', content: reply });
                chatHistory.value = res.data.history || apiMessages.concat([{ role: 'assistant', content: reply }]);
            } catch (e) {
                chatMessages.value.push({ role: 'assistant', content: '请求失败: ' + e.message });
            }

            chatLoading.value = false;
            await nextTick();
            if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight;
        }

        // ==================== 初始化 ====================
        onMounted(async () => {
            try {
                // 快速加载核心数据
                await loadStats();

                // 延迟加载AI提供商列表
                setTimeout(() => loadProviders(), 500);
            } catch (e) {
                console.error('初始化失败:', e);
            } finally {
                // 最短显示300ms加载动画
                setTimeout(() => {
                    isLoading.value = false;
                }, 300);
            }
        });

        return {
            isLoading, currentPage, stats, persons, selectedUser, navItems, homeCards,
            // 案件管理
            currentCaseId, cases, onCaseChange,
            showCreateCaseDialog, newCaseId, newCaseName, creatingCase, doCreateCase,
            // 导入
            doClear,
            // 证据导入
            evidenceFiles, evidenceFileList, evidenceType, evidenceDesc, evidenceUploading, evidenceResults, doEvidenceUpload,
            // 分析
            analysisData, anomalyData, counterparts, analysisSummary,
            analysisLoading, activeAnalysisTab,
            loadAnalysis, chartMonthly, chartHour, chartCounterpart, onAnalysisTabChange,
            // 图谱
            graphData, graphLoading, graphIframeSrc, loadGraph,
            relationTargetUser, relationshipData, relationshipLoading, relationshipIframeSrc, analyzeRelationship,
            // 画像
            profileData, profileLoading, profileExpanded, loadProfile, downloadReport,
            // Agent
            chatMessages, chatHistory, chatInput, chatLoading, chatBox,
            providers, agentConfig, showApiKey, currentProviderModels, sampleQuestions,
            onProviderChange, sendChat, renderMd,
            // 财付通验证
            tenpayValidation, checkTenpayPair,
        };
    }
});

app.use(ElementPlus);
app.mount('#app');
