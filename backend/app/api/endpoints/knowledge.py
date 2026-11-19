"""知识库接口：上传/入库/检索/列表"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.base import get_db
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.rag.pipeline import ingest_document, ingest_text, retrieve
from app.api.deps import require_role, get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.core.config import settings
from pathlib import Path

router = APIRouter()


@router.post("/documents/upload", response_model=ApiResponse)
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role("ADMIN"))):
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / file.filename
    content = await file.read()
    path.write_bytes(content)
    result = await ingest_document(db, str(path))
    return ApiResponse(data=result)


from pydantic import BaseModel, Field
class IngestTextRequest(BaseModel):
    filename: str
    text: str = Field(min_length=10)


@router.post("/documents/ingest-text", response_model=ApiResponse)
async def ingest_text_api(req: IngestTextRequest, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_role("ADMIN"))):
    result = await ingest_text(db, req.filename, req.text)
    return ApiResponse(data=result)


@router.post("/search", response_model=ApiResponse)
async def search_knowledge(query: str, top_k: int = 5,
                           db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    results = await retrieve(db, query, top_k)
    return ApiResponse(data={"query": query, "results": results})


@router.get("/documents", response_model=ApiResponse)
async def list_documents(db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    result = await db.execute(select(KnowledgeDocument).order_by(desc(KnowledgeDocument.created_at)))
    docs = result.scalars().all()
    return ApiResponse(data=[{
        "id": d.id, "filename": d.filename, "file_type": d.file_type,
        "status": d.status, "chunk_count": d.chunk_count,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    } for d in docs])


@router.get("/stats", response_model=ApiResponse)
async def knowledge_stats(db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    docs = (await db.execute(select(KnowledgeDocument))).scalars().all()
    chunks = (await db.execute(select(KnowledgeChunk))).scalars().all()
    return ApiResponse(data={
        "documents": len(docs), "chunks": len(chunks),
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_dim": settings.EMBEDDING_DIM,
    })
