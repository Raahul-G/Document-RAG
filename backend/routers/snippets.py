from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.snippet import SnippetError, render_page_png

router = APIRouter(prefix="/snippets", tags=["snippets"])


@router.get("/render")
def render_snippet(
    doc_name: str = Query(..., description="Document original_name"),
    page: int = Query(..., ge=1, description="1-based page number"),
    text: str = Query("", description="Passage text used to derive highlight phrase"),
    passage_index: int | None = Query(None, ge=1, description="1-based passage index; when supplied the stored chunk text is used for highlighting instead of *text*"),
    db: Session = Depends(get_db),
):
    """
    Render a PDF page as PNG with the cited passage highlighted.

    Returns:
        200 image/png  — page render with yellow highlight
        404            — document not found in DB
        501            — document is not a PDF (e.g. DOCX)
        422            — invalid query parameters (FastAPI default)
    """
    try:
        png_bytes = render_page_png(doc_name, page, text, db, passage_index=passage_index)
    except SnippetError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "only supported for pdf" in msg.lower():
            raise HTTPException(status_code=501, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
