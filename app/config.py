from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

# 测试阶段默认打开项目目录中的示例 PDF，用户仍可通过“打开 PDF”切换文件。
DEFAULT_PDF = APP_DIR / "Hello-Agents-V1.0.2-20260210.pdf"

WINDOW_TITLE = "Scrollette"
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# LLM：通义千问 / DashScope（OpenAI 兼容接口）。换模型只改这里。
LLM_API_KEY_ENV = "DASHSCOPE_API_KEY"  # 从该环境变量读取 key，绝不写进源码
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen-plus"
