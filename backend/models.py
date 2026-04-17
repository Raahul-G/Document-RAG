from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String, unique=True, index=True)  # stored filename
    original_name: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)  # pdf, docx
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, processing, indexed, failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    passage_index: Mapped[int] = mapped_column(Integer)  # sequential index within page
    section_title: Mapped[str] = mapped_column(String, default="")
    text: Mapped[str] = mapped_column(Text)
    chroma_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String, default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of citation objects
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    session: Mapped["Session"] = relationship("Session", back_populates="messages")
