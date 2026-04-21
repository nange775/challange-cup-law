"""项目配置"""
import os
import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """获取资源文件路径（兼容打包后和开发环境）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，资源在 _MEIPASS 临时目录
        base_path = Path(sys._MEIPASS)
    else:
        # 开发环境
        base_path = Path(__file__).parent
    return base_path / relative_path


def get_data_path(relative_path: str) -> Path:
    """获取数据文件路径（用户可写目录）"""
    if getattr(sys, 'frozen', False):
        # 打包后：使用可执行文件所在目录
        base_path = Path(sys.executable).parent
    else:
        # 开发环境
        base_path = Path(__file__).parent
    return base_path / relative_path


# 路径配置
PROJECT_ROOT = Path(__file__).parent if not getattr(sys, 'frozen', False) else Path(sys.executable).parent
DATA_DIR = get_data_path("data")
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
# LLM API Keys 配置
# ============================================================
# 在这里直接配置 API Key，无需设置环境变量
# 如果不想在代码中暴露 API Key，可以留空，系统会自动从环境变量读取

ANTHROPIC_API_KEY = ""  # Anthropic Claude API Key
OPENAI_API_KEY = ""     # OpenAI GPT API Key
DEEPSEEK_API_KEY = ""   # DeepSeek API Key
QWEN_API_KEY = "sk-3809d9b01f0b486ea7276e1cfa093a6a"       # 通义千问 API Key（在此填写你的 Key）
ZHIPU_API_KEY = ""      # 智谱 GLM API Key
MOONSHOT_API_KEY = ""   # Moonshot Kimi API Key

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
    """读取指定厂商的 API Key（优先读取 config.py 中的变量，其次读取环境变量）"""
    provider = LLM_PROVIDERS.get(provider_id, {})
    env_key = provider.get("env_key", "")

    if not env_key:
        return ""

    # 1. 优先从 config.py 中读取（检查全局变量）
    if env_key in globals():
        api_key = globals()[env_key]
        if api_key:
            return api_key

    # 2. 其次从环境变量读取
    return os.environ.get(env_key, "")


# ============================================================
# OCR 配置
# ============================================================
# Tesseract OCR 可执行文件路径（Windows/Linux/Mac）
# Windows: r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# Linux: '/usr/bin/tesseract'
# Mac: '/usr/local/bin/tesseract' (通过 Homebrew 安装)
TESSERACT_CMD = os.environ.get('TESSERACT_CMD', '/usr/bin/tesseract')

# OCR 支持的图像格式
OCR_SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']

# OCR 语言配置（支持中英文）
OCR_LANG = 'chi_sim+eng'  # 简体中文 + 英文
