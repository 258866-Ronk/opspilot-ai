"""知识文档表 + 知识切片表（RAG 用）"""
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


def _now():
    return datetime.now(timezone.utc)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PROCESSING")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    # 注意：metadata 是 SQLAlchemy 保留属性名，故属性叫 meta_data，数据库列名仍为 "metadata"
    meta_data: Mapped[dict | None] = mapped_column("metadata", JSON)
    # 向量存储：SQLite 下用 JSON 数组；PostgreSQL 下可切换为 pgvector VECTOR 类型
    embedding: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
