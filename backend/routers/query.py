import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Message
from backend.models import Session as ChatSession
from backend.schemas import CitationSource, QueryIn, QueryOut
from backend.services import generation, retrieval
from backend.services.retrieval import NOT_FOUND_THRESHOLD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


def _get_or_create_session(session_id: int | None, question: str, db: Session) -> ChatSession:
    """Return existing session or create a new one titled from the first question."""
    if session_id:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    title = question[:60] + ("…" if len(question) > 60 else "")
    session = ChatSession(title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("", response_model=QueryOut)
def query_documents(payload: QueryIn, db: Session = Depends(get_db)):
    # 1. Retrieve — hybrid search + rerank
    chunks, top_score = retrieval.retrieve(
        query=payload.question,
        doc_ids=payload.doc_filter or None,
    )

    logger.info("Query: %r | top_score=%.2f | chunks=%d", payload.question, top_score, len(chunks))

    # 2. Threshold gate — don't call Gemini if nothing relevant found
    if not chunks or top_score < NOT_FOUND_THRESHOLD:
        session = _get_or_create_session(payload.session_id, payload.question, db)
        msg = Message(
            session_id=session.id,
            question=payload.question,
            answer="",
            sources_json="[]",
        )
        db.add(msg)
        db.commit()
        return QueryOut(
            answer="I could not find an answer to this question in the uploaded documents.",
            found=False,
            sources=[],
            session_id=session.id,
        )

    # 3. Generate answer via Gemini
    try:
        result = generation.generate_answer(payload.question, chunks)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 4. Persist session + message
    session = _get_or_create_session(payload.session_id, payload.question, db)
    sources = [CitationSource(**s) for s in result["sources"]]
    msg = Message(
        session_id=session.id,
        question=payload.question,
        answer=result["answer"],
        sources_json=json.dumps(result["sources"]),
    )
    db.add(msg)
    db.commit()

    return QueryOut(
        answer=result["answer"],
        found=result["found"],
        sources=sources,
        session_id=session.id,
    )
