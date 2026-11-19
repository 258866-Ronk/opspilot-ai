"""文档加载：PDF / TXT / Markdown"""
from pathlib import Path


def load_document(file_path: str) -> tuple[str, dict]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    metadata = {"filename": path.name, "file_type": suffix}

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("需要安装 pypdf：pip install pypdf")
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        metadata["pages"] = len(reader.pages)
    elif suffix in (".txt", ".md", ".markdown"):
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"不支持的文件类型：{suffix}")

    return text, metadata
