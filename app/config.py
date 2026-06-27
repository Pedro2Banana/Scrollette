from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

# 测试阶段默认打开项目目录中的示例 PDF，用户仍可通过“打开 PDF”切换文件。
BOOKS_DIR = APP_DIR / "books"  # 书籍统一放这里，可放多本
DEFAULT_PDF = BOOKS_DIR / "Hello-Agents-V1.0.2-20260210.pdf"

WINDOW_TITLE = "Scrollette"
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# LLM：通义千问 / DashScope（OpenAI 兼容接口）。换模型只改这里。
LLM_API_KEY_ENV = "DASHSCOPE_API_KEY"  # 从该环境变量读取 key，绝不写进源码
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen-plus"

# Embedding（向量化，复用同一 key / base_url）
EMBED_MODEL = "text-embedding-v3"
EMBED_BATCH = 10  # 每次请求的文本条数上限

# 运行时生成的数据统一放项目根的 data/（已 gitignore），与 app/ 源码分开。
DATA_DIR = APP_DIR / "data"

# SQLite（阅读元数据等）
DB_PATH = DATA_DIR / "scrollette.db"

# RAG 向量库（Chroma 本地持久化）
RAG_INDEX_DIR = DATA_DIR / "rag_index"
RAG_COLLECTION = "document_chunks"
RAG_TOP_K = 5  # 检索返回的 chunk 数
