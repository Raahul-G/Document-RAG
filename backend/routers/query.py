import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
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
    # 1. Load conversation history first — needed for query rewriting
    history: list[dict] = []
    if payload.session_id:
        recent = (
            db.query(Message)
            .filter(Message.session_id == payload.session_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        history = [
            {"question": m.question, "answer": m.answer}
            for m in reversed(recent)
            if m.answer  # skip gate-1 misses that have no answer
        ]

    # 2. Rewrite query to resolve anaphoric references before retrieval
    retrieval_query = generation.rewrite_query(payload.question, history)
    if retrieval_query != payload.question:
        logger.info("Query rewritten: %r → %r", payload.question, retrieval_query)

    # 3. Retrieve — hybrid search + soft reranking (uses rewritten query)
    chunks, coverage_ok = retrieval.retrieve(
        query=retrieval_query,
        doc_ids=payload.doc_filter or None,
    )

    # 4. Gate 1: coverage check (retrieval signals, not cross-encoder score)
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

    # 5. Generate answer — always uses original question (rewrite is retrieval-only)
    #    Gate 2: LLM self-checks via found:false — it decides if chunks answer the question
    if history:
        logger.info("Passing %d history turn(s) to LLM for session %d", len(history), payload.session_id)
    try:
        result = generation.generate_answer(payload.question, chunks, history=history or None)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Gemini is instructed to cite exact passages but often paraphrases the text
    # field in its JSON response.  Restore the original retrieved chunk text so
    # the snippet highlighter always searches for text that actually exists in
    # the PDF verbatim.
    _chunk_text_by_key = {
        (c["metadata"]["doc_name"], c["metadata"]["page_number"], c["metadata"]["passage_index"]): c["text"]
        for c in chunks
    }
    for src in result.get("sources", []):
        key = (src.get("doc_name"), src.get("page"), src.get("passage_index"))
        if key in _chunk_text_by_key:
            src["text"] = _chunk_text_by_key[key]

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


# ── Streaming endpoint ────────────────────────────────────────────────────────

def _chunk_to_source(c: dict) -> dict:
    meta = c["metadata"]
    return {
        "doc_name": meta["doc_name"],
        "page": meta["page_number"],
        "passage_index": meta["passage_index"],
        "section_title": meta.get("section_title", ""),
        "text": c["text"],
    }


@router.post("/stream")
def query_documents_stream(payload: QueryIn, db: Session = Depends(get_db)):
    """
    SSE streaming endpoint.

    Events (newline-delimited JSON after 'data: '):
      {"type": "token",  "text": str}
      {"type": "done",   "found": bool, "answer": str, "sources": [...], "session_id": int}
      {"type": "error",  "message": str}
    """
    # 1. Load history first — needed for query rewriting (injected db is safe here)
    history: list[dict] = []
    if payload.session_id:
        recent = (
            db.query(Message)
            .filter(Message.session_id == payload.session_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        history = [
            {"question": m.question, "answer": m.answer}
            for m in reversed(recent)
            if m.answer
        ]

    # 2. Rewrite query to resolve anaphoric references before retrieval
    retrieval_query = generation.rewrite_query(payload.question, history)
    if retrieval_query != payload.question:
        logger.info("Query rewritten: %r → %r", payload.question, retrieval_query)

    # 3. Retrieve — must happen before generator starts (uses injected db)
    chunks, coverage_ok = retrieval.retrieve(
        query=retrieval_query,
        doc_ids=payload.doc_filter or None,
    )

    # 4. Gate 1 — short-circuit before streaming
    if not coverage_ok:
        session = _get_or_create_session(payload.session_id, payload.question, db)
        db.add(Message(session_id=session.id, question=payload.question,
                       answer="", sources_json="[]"))
        db.commit()
        not_found_msg = "I could not find an answer to this question in the uploaded documents."

        def _not_found():
            payload = json.dumps({
                "type": "done", "found": False, "answer": not_found_msg,
                "sources": [], "session_id": session.id,
            })
            yield f"data: {payload}\n\n"

        return StreamingResponse(_not_found(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # 4. Pre-create / resolve session while injected db is still reliable
    chat_session = _get_or_create_session(payload.session_id, payload.question, db)
    session_id = chat_session.id
    question = payload.question

    # All retrieved chunks are candidate sources (streaming mode — no per-passage
    # citation from Gemini, so expose everything the retriever ranked).
    candidate_sources = [_chunk_to_source(c) for c in chunks]

    def event_stream():
        answer_parts: list[str] = []
        found = False

        yield f'data: {json.dumps({"type": "status", "status": "Generating answer..."})}\n\n'

        try:
            for event in generation.stream_answer(question, chunks, history or None):
                if event["type"] == "token":
                    answer_parts.append(event["text"])
                    yield f'data: {json.dumps({"type": "token", "text": event["text"]})}\n\n'
                elif event["type"] == "done":
                    found = event["found"]
        except RuntimeError as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'
            return

        full_answer = "".join(answer_parts) if found else ""
        sources_data = candidate_sources if found else []

        # Save to DB using a fresh session (injected session may be closed by now)
        db_write = SessionLocal()
        try:
            db_write.add(Message(
                session_id=session_id,
                question=question,
                answer=full_answer,
                sources_json=json.dumps(sources_data),
            ))
            db_write.commit()
        except Exception as exc:
            logger.error("Failed to persist streamed message: %s", exc)
        finally:
            db_write.close()

        payload = json.dumps({
            "type": "done", "found": found, "answer": full_answer,
            "sources": sources_data, "session_id": session_id,
        })
        yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
