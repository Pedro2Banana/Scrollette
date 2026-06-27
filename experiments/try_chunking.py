"""直观看看一页 PDF 被切成了什么样。

用法（在项目根目录）：
    python experiments/try_chunking.py [页码]   # 页码从 1 起，默认 11
"""
import pathlib
import sys

# 让脚本无论从哪儿启动都能 import 到 app 包。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_PDF
from app.rag.chunker import chunk_page
from app.reader.pdf_document import PdfDocument


def main():
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 11  # 1-based

    doc = PdfDocument()
    doc.open(DEFAULT_PDF)
    text = doc.page_text(page - 1)
    doc.close()

    chunks = chunk_page(text, page_number=page)
    print(f"第 {page} 页：{len(text)} 字 → 切成 {len(chunks)} 块\n")
    for c in chunks:
        print(f"--- chunk {c.chunk_index}  ({len(c.text)} 字) ---")
        print(c.text)
        print()


if __name__ == "__main__":
    main()
