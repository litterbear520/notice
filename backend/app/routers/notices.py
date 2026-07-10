import json

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Notice

router = APIRouter(prefix="/api")


@router.get("/notices")
def list_notices(
    source_id: int | None = None,
    matched_only: bool = True,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_session),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    stmt = select(Notice)
    if source_id:
        stmt = stmt.where(Notice.source_id == source_id)
    if matched_only:
        stmt = stmt.where(Notice.matched == True)  # noqa: E712
    if q:
        stmt = stmt.where(Notice.title.contains(q))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Notice.published_at.desc(), Notice.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": n.id,
                "source_id": n.source_id,
                "source_name": n.source.name,
                "title": n.title,
                "url": n.url,
                "excerpt": (n.content or "")[:300],
                "published_at": n.published_at,
                "matched": n.matched,
                "matched_keywords": json.loads(n.matched_keywords or "[]"),
            }
            for n in rows
        ],
    }
