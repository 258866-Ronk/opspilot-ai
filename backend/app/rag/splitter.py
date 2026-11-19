"""文本切片模块：优先用 langchain-text-splitters，未安装则用内置实现"""
from app.core.logging import logger


def split_text(text: str, chunk_size: int = 600, chunk_overlap: int = 80, source: str = "") -> list[dict]:
    """
    返回 [{"content":..., "metadata":...}, ...]
    中文运维文档建议 300~800 字切片，overlap 保留上下文。
    """
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            length_function=len,
        )
        docs = splitter.create_documents([text])
        return [{"content": d.page_content, "metadata": {"source": source, **d.metadata}} for d in docs]
    except ImportError:
        logger.debug("langchain-text-splitters not installed, using builtin splitter")
        return _builtin_split(text, chunk_size, chunk_overlap, source)


def _builtin_split(text, chunk_size, chunk_overlap, source):
    """内置切片：按句号/换行优先切，简单但够用"""
    paragraphs = [p.strip() for p in text.replace("\r", "").split("\n") if p.strip()]
    chunks, buf = [], ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= chunk_size:
            buf += p + "\n"
        else:
            if buf:
                chunks.append(buf.strip())
                tail = buf[-chunk_overlap:] if chunk_overlap else ""
                buf = tail + p + "\n"
            else:
                chunks.append(p[:chunk_size])
                buf = p[chunk_size - chunk_overlap:] if chunk_overlap else ""
    if buf.strip():
        chunks.append(buf.strip())
    return [{"content": c, "metadata": {"source": source}} for c in chunks if c]
