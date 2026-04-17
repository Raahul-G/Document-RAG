from fastapi import APIRouter
from backend.schemas import QueryIn, QueryOut

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryOut)
def query_documents(payload: QueryIn):
    # Placeholder — retrieval + generation pipeline built in Milestone 4
    return QueryOut(
        answer="Retrieval pipeline not yet implemented.",
        found=False,
        sources=[],
        session_id=payload.session_id or 0,
    )
