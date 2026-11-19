"""
RAG Pipeline：入库 + 检索
=========================
完整流程：
  入库：文档 → 切片 → Embedding → 存 knowledge_chunks 表
  检索：问题 → Embedding → 余弦相似度（本地）或 pgvector（生产）→ 重排 → 返回证据

面试点：
  - 为什么切片要 overlap？避免答案被切断在边界。
  - 为什么用余弦相似度？因为向量做了归一化，余弦 = 点积，计算快且不受长度影响。
  - 混合检索/重排是进阶优化：先召回多个，再用 rerank 模型精排。
"""
from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.rag.loader import load_document
from app.rag.splitter import split_text
from app.rag.embedding import get_embedder, cosine_similarity


async def ingest_document(session: AsyncSession, file_path: str) -> dict:
    """把文档切片入库"""
    text, meta = load_document(file_path)
    chunks = split_text(text, source=meta["filename"])
    embedder = get_embedder()
    vectors = embedder.embed([c["content"] for c in chunks])

    doc = KnowledgeDocument(
        filename=meta["filename"], file_path=file_path,
        file_type=meta["file_type"], status="PROCESSING",
    )
    session.add(doc)
    await session.flush()

    for c, vec in zip(chunks, vectors):
        session.add(KnowledgeChunk(
            document_id=doc.id, content=c["content"],
            meta_data=c["metadata"], embedding=vec,
        ))

    doc.chunk_count = len(chunks)
    doc.status = "READY"
    await session.commit()
    logger.info("Ingested %s: %d chunks", meta["filename"], len(chunks))
    return {"document_id": doc.id, "filename": meta["filename"], "chunks": len(chunks)}


async def ingest_text(session: AsyncSession, filename: str, text: str) -> dict:
    """直接入库文本（用于演示文档，无需上传文件）"""
    chunks = split_text(text, source=filename)
    embedder = get_embedder()
    vectors = embedder.embed([c["content"] for c in chunks])
    doc = KnowledgeDocument(filename=filename, file_type=".txt", status="PROCESSING")
    session.add(doc)
    await session.flush()
    for c, vec in zip(chunks, vectors):
        session.add(KnowledgeChunk(document_id=doc.id, content=c["content"],
                                   meta_data=c["metadata"], embedding=vec))
    doc.chunk_count = len(chunks)
    doc.status = "READY"
    await session.commit()
    return {"document_id": doc.id, "filename": filename, "chunks": len(chunks)}


async def retrieve(session: AsyncSession, query: str, top_k: int = 4) -> list[dict]:
    """向量检索：把 query 向量化，与库里所有切片算相似度，取 Top-K"""
    embedder = get_embedder()
    qvec = embedder.embed_query(query)

    result = await session.execute(select(KnowledgeChunk))
    chunks = result.scalars().all()
    if not chunks:
        return []

    scored = []
    for ch in chunks:
        sim = cosine_similarity(qvec, ch.embedding or [])
        scored.append((sim, ch))
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, ch in scored[:top_k]:
        results.append({
            "chunk_id": ch.id, "document_id": ch.document_id,
            "content": ch.content, "metadata": ch.meta_data,
            "score": round(sim, 4),
        })
    return results


async def rag_search(session: AsyncSession, query: str, top_k: int = 4) -> dict:
    """供 Agent 工具调用的封装"""
    results = await retrieve(session, query, top_k)
    evidence = "\n\n".join(f"[证据{i+1} 相似度{r['score']:.2f}]\n{r['content']}"
                           for i, r in enumerate(results))
    return {
        "success": True,
        "query": query,
        "results": results,
        "evidence": evidence or "知识库中没有相关内容",
        "analysis_hint": f"检索到 {len(results)} 条相关知识" if results else "无匹配知识",
    }
