import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Message
from backend.models import Session as ChatSession
from backend.schemas import CitationSource, QueryIn, QueryOut
from backend.services import generation, retrieval

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 5  # number of prior Q&A turns passed to Gemini

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
    # 1. Retrieve — hybrid search + soft reranking
    chunks, coverage_ok = retrieval.retrieve(
        query=payload.question,
        doc_ids=payload.doc_filter or None,
    )

    # 2. Gate 1: coverage check (retrieval signals, not cross-encoder score)
    if not coverage_ok:
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

    # 3. Load conversation history from the current session (if any)
    history: list[dict] = []
    if payload.session_id:
        recent = (
            db.query(Message)
            .filter(Message.session_id == payload.session_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        # reverse so oldest turn comes first
        history = [
            {"question": m.question, "answer": m.answer}
            for m in reversed(recent)
            if m.answer  # skip gate-1 misses that have no answer
        ]
        if history:
            logger.info("Passing %d history turn(s) to Gemini for session %d", len(history), payload.session_id)

    # 4. Generate answer via Gemini
    #    Gate 2: Gemini self-checks via found:false — it decides if chunks answer the question
    try:
        result = generation.generate_answer(payload.question, chunks, history=history or None)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 5. Persist session + message
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
