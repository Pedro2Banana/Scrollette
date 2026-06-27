from dataclasses import dataclass


@dataclass
class Chunk:
    page_number: int
    chunk_index: int
    text: str


def chunk_page(text, page_number, chunk_size=500, overlap=80):
    """Split one page's plain text into overlapping chunks.

    v0 strategy: greedily pack lines/paragraphs up to ~chunk_size chars; if a
    single piece is longer, hard-split it; then carry the previous chunk's tail
    (``overlap`` chars) into the next so context isn't cut at the seam.

    Pure function — no Qt, no I/O — so it's trivially testable.
    """
    text = (text or "").strip()
    if not text:
        return []

    # PDF 文本多是按视觉行断的单换行，这里把非空行当作最小段落单位。
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # 1) 贪心打包成不超过 chunk_size 的片段；单段过长则按长度硬切。
    pieces = []
    buf = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if buf:
                pieces.append(buf)
                buf = ""
            for i in range(0, len(para), chunk_size):
                pieces.append(para[i:i + chunk_size])
        elif len(buf) + len(para) + 1 <= chunk_size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            pieces.append(buf)
            buf = para
    if buf:
        pieces.append(buf)

    # 2) 给每块开头接上前一块的尾部 overlap 个字，做上下文衔接。
    chunks = []
    prev_tail = ""
    for index, piece in enumerate(pieces):
        body = prev_tail + piece if prev_tail else piece
        chunks.append(Chunk(page_number=page_number, chunk_index=index, text=body))
        prev_tail = piece[-overlap:] if overlap > 0 else ""
    return chunks
