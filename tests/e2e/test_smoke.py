"""
E2E smoke tests for the Document RAG API.

Requires a running server: uv run uvicorn backend.main:app --reload
Run with:  uv run pytest tests/e2e/ -v

Tests (in order):
  1. Health — server is up and serving
  2. Documents — list endpoint responds
  3. Sessions — list endpoint responds
  4. Query (no docs) — returns 200 with found:false gracefully
  5. Upload — POST a real PDF-like file, get 202
  6. Query after upload — retrieval pipeline runs, Gemini called (may return found:false if quota)
  7. Conversational follow-up — second query in same session includes history
  8. Session persistence — session contains both messages
  9. Streaming — /query/stream returns SSE content-type and done event
  9. Session delete — cleans up
"""
from __future__ import annotations

import io
import time

import pytest
import httpx

BASE_URL = "http://127.0.0.1:8000/api"
TIMEOUT = 60.0  # Gemini can be slow on first call


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
        yield c


# ── 1. Health ─────────────────────────────────────────────────────────────────

def test_server_is_up(client):
    r = client.get("/documents")
    assert r.status_code == 200


# ── 2. Documents list ─────────────────────────────────────────────────────────

def test_documents_list_returns_list(client):
    r = client.get("/documents")
    data = r.json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


# ── 3. Sessions list ──────────────────────────────────────────────────────────

def test_sessions_list_returns_list(client):
    r = client.get("/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── 4. Query with no session — returns 200 even if found:false ────────────────

def test_query_no_session_graceful(client):
    r = client.post("/query", json={"question": "What is the meaning of life?"})
    assert r.status_code in (200, 503)  # 503 only if Gemini quota exhausted
    if r.status_code == 200:
        data = r.json()
        assert "answer" in data
        assert "found" in data
        assert "session_id" in data


# ── 5. Upload a minimal PDF ───────────────────────────────────────────────────

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
    b"/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1"
    b"/BaseFont/Helvetica>>>>>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
    b"endstream endobj\n"
    b"xref\n0 5\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000274 00000 n \n"
    b"trailer<</Size 5/Root 1 0 R>>\n"
    b"startxref\n370\n%%EOF"
)


@pytest.fixture(scope="module")
def uploaded_doc_id(client):
    """Upload a test PDF and return its doc_id. Cleans up after the module."""
    files = {"file": ("smoke_test.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")}
    r = client.post("/documents/upload", files=files)
    assert r.status_code == 202, f"Upload failed: {r.text}"
    doc_id = r.json()["id"]

    # Wait for indexing (up to 30 s)
    for _ in range(30):
        status_r = client.get("/documents")
        docs = status_r.json().get("documents", [])
        doc = next((d for d in docs if d["id"] == doc_id), None)
        if doc and doc["status"] in ("indexed", "failed"):
            break
        time.sleep(1)

    yield doc_id

    # Cleanup
    client.delete(f"/documents/{doc_id}")


def test_upload_returns_202(client):
    files = {"file": ("check.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")}
    r = client.post("/documents/upload", files=files)
    # May return 409 if file hash already exists — both are acceptable
    assert r.status_code in (202, 409)


# ── 6. Query after upload ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def first_query_session_id(client, uploaded_doc_id):
    """Run a first query and return (session_id, answer)."""
    r = client.post("/query", json={
        "question": "What text appears in this document?",
        "doc_filter": [uploaded_doc_id],
    })
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        pytest.skip("Gemini quota exhausted — skipping downstream tests")
    data = r.json()
    return data["session_id"], data.get("answer", "")


def test_query_after_upload_returns_session(client, first_query_session_id):
    session_id, _ = first_query_session_id
    assert isinstance(session_id, int)
    assert session_id > 0


# ── 7. Conversational follow-up ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def followup_response(client, first_query_session_id, uploaded_doc_id):
    session_id, _ = first_query_session_id
    r = client.post("/query", json={
        "question": "Can you summarize that in one sentence?",
        "session_id": session_id,
        "doc_filter": [uploaded_doc_id],
    })
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        pytest.skip("Gemini quota exhausted")
    return r.json(), session_id


def test_followup_uses_same_session(client, followup_response):
    data, original_session_id = followup_response
    assert data["session_id"] == original_session_id


def test_followup_returns_answer_field(client, followup_response):
    data, _ = followup_response
    assert "answer" in data
    assert "found" in data


# ── 8. Session contains both messages ─────────────────────────────────────────

def test_session_has_two_messages(client, followup_response):
    _, session_id = followup_response
    r = client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) >= 2  # initial query + follow-up


def test_session_messages_have_questions(client, followup_response):
    _, session_id = followup_response
    r = client.get(f"/sessions/{session_id}")
    messages = r.json()["messages"]
    questions = [m["question"] for m in messages]
    assert any("text" in q.lower() or "document" in q.lower() for q in questions)


# ── 9. Session delete ─────────────────────────────────────────────────────────

def test_delete_session(client, first_query_session_id):
    session_id, _ = first_query_session_id
    r = client.delete(f"/sessions/{session_id}")
    assert r.status_code == 200
    # Verify it's gone
    r2 = client.get(f"/sessions/{session_id}")
    assert r2.status_code == 404


# ── 9. Streaming endpoint ─────────────────────────────────────────────────────

def _parse_sse(raw: str) -> list[dict]:
    """Parse SSE response body into a list of event dicts."""
    import json
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def test_stream_endpoint_content_type(client):
    """Streaming endpoint must return text/event-stream."""
    with client.stream("POST", "/query/stream",
                       json={"question": "Hello, what is in the document?"},
                       headers={"Accept": "text/event-stream"}) as r:
        assert "text/event-stream" in r.headers.get("content-type", "")


def test_stream_endpoint_has_done_event(client, uploaded_doc_id):
    """Streaming response must end with a 'done' event containing session_id."""
    with client.stream("POST", "/query/stream",
                       json={"question": "What text appears in this document?",
                             "doc_filter": [uploaded_doc_id]}) as r:
        if r.status_code == 503:
            pytest.skip("Gemini quota exhausted")
        assert r.status_code == 200
        body = r.read().decode()

    events = _parse_sse(body)
    assert events, "No SSE events received"

    done_events = [e for e in events if e.get("type") == "done"]
    assert done_events, "No 'done' event in stream"
    done = done_events[-1]
    assert "found" in done
    assert "session_id" in done
    assert isinstance(done["session_id"], int)

    # Clean up the session created by this test
    if done.get("session_id"):
        client.delete(f"/sessions/{done['session_id']}")


def test_stream_token_events_are_strings(client, uploaded_doc_id):
    """All token events must have string text fields."""
    with client.stream("POST", "/query/stream",
                       json={"question": "Describe the document.",
                             "doc_filter": [uploaded_doc_id]}) as r:
        if r.status_code == 503:
            pytest.skip("Gemini quota exhausted")
        body = r.read().decode()

    events = _parse_sse(body)
    token_events = [e for e in events if e.get("type") == "token"]
    for e in token_events:
        assert isinstance(e["text"], str)

    if token_events:
        done = next((e for e in events if e.get("type") == "done"), None)
        if done and done.get("session_id"):
            client.delete(f"/sessions/{done['session_id']}")
