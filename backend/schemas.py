from datetime import datetime

from pydantic import BaseModel


# --- Document ---

class DocumentOut(BaseModel):
    id: int
    original_name: str
    file_type: str
    page_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]


# --- Query ---

class QueryIn(BaseModel):
    question: str
    session_id: int | None = None
    doc_filter: list[int] | None = None  # document IDs to scope search


class CitationSource(BaseModel):
    doc_name: str
    page: int
    passage_index: int
    section_title: str
    text: str


class QueryOut(BaseModel):
    answer: str
    found: bool
    sources: list[CitationSource]
    session_id: int


# --- Sessions ---

class SessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    question: str
    answer: str
    sources_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetailOut(BaseModel):
    session: SessionOut
    messages: list[MessageOut]
