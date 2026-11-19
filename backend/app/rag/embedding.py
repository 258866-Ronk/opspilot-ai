"""
Embedding 封装：双栈设计
=======================
- 默认 local：用「字符 n-gram 哈希」生成向量。零依赖、零模型下载，
  效果虽不如语义模型，但能完整演示 RAG 全流程（切片→向量化→检索→重排）。
- 可选 model：填了 EMBEDDING_PROVIDER=model 且装了 sentence-transformers，
  用真实 BGE 中文模型（语义效果更好）。

面试要点：
  - 向量维度必须与存储一致（config 里 EMBEDDING_DIM）。
  - 真实项目要处理「模型版本切换」——换模型必须重新向量化全库，否则向量空间不一致。
"""
import hashlib
import numpy as np
from app.core.config import settings
from app.core.logging import logger


class LocalHashEmbedding:
    """字符级哈希向量：把文本映射成固定维度向量（演示用途）"""
    def __init__(self, dim: int = 384):
        self.dim = dim

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        text = text.lower().strip()
        # 用 unigram + bigram 提升区分度
        tokens = list(text) + [text[i:i+2] for i in range(len(text) - 1)]
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % self.dim
            vec[idx] += 1.0
        # L2 归一化（余弦相似度需要）
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t).tolist() for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text).tolist()


class ModelEmbedding:
    """真实 BGE 模型（可选）"""
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        if settings.EMBEDDING_PROVIDER == "model":
            try:
                _embedder = ModelEmbedding(settings.EMBEDDING_MODEL)
                logger.info("Using real embedding model: %s (dim=%d)", settings.EMBEDDING_MODEL, _embedder.dim)
            except Exception as e:
                logger.warning("Failed to load model embedding (%s), falling back to local", e)
                _embedder = LocalHashEmbedding(settings.EMBEDDING_DIM)
        else:
            _embedder = LocalHashEmbedding(settings.EMBEDDING_DIM)
    return _embedder


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
