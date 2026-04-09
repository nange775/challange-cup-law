"""项目配置"""
import os
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "investigation.db"

# 分析参数
STRUCTURING_WINDOW_MINUTES = 60      # 化整为零检测时间窗口(分钟)
STRUCTURING_MIN_COUNT = 3            # 化整为零最少交易笔数
ABNORMAL_HOUR_START = 0              # 异常时段开始(时)
ABNORMAL_HOUR_END = 6                # 异常时段结束(时)
WEALTH_SURGE_THRESHOLD = 2.0         # 财富突增倍数阈值(相对月均)
HIGH_FREQ_COUNTERPART_THRESHOLD = 30 # 高频对手方月交易笔数阈值
LARGE_AMOUNT_THRESHOLD = 500000      # 大额交易阈值(分, 即5000元)

# ============================================================
# LLM 多厂商配置
# ============================================================
# protocol: "anthropic" 用 anthropic SDK, "openai" 用 openai SDK (兼容大部分国内厂商)

LLM_PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base_url": None,
        "default_model": "claude-sonnet-4-20250514",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-20250514"],
        "protocol": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "name": "OpenAI (GPT)",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
        "protocol": "openai",
        "env_key": "OPENAI_API_KEY",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "protocol": "openai",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "protocol": "openai",
        "env_key": "QWEN_API_KEY",
    },
    "zhipu": {
        "name": "智谱 (GLM)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-long"],
        "protocol": "openai",
        "env_key": "ZHIPU_API_KEY",
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-32k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "protocol": "openai",
        "env_key": "MOONSHOT_API_KEY",
    },
    "custom": {
        "name": "自定义 (OpenAI 兼容)",
        "base_url": "",
        "default_model": "",
        "models": [],
        "protocol": "openai",
        "env_key": "",
    },
}


def get_provider_api_key(provider_id: str) -> str:
    """从环境变量读取指定厂商的 API Key"""
    provider = LLM_PROVIDERS.get(provider_id, {})
    env_key = provider.get("env_key", "")
    return os.environ.get(env_key, "") if env_key else ""
