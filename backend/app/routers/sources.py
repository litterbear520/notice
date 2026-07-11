from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipeline
from ..auth import get_current_admin
from ..db import get_session
from ..models import Source

router = APIRouter(prefix="/api")


class SourceCreate(BaseModel):
    name: str
    type: str
    url: str


class SourcePatch(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


def _to_dict(s: Source) -> dict:
    return {
        "id": s.id, "name": s.name, "type": s.type, "url": s.url,
        "enabled": s.enabled, "is_builtin": s.is_builtin,
        "last_fetch_at": s.last_fetch_at, "last_fetch_status": s.last_fetch_status,
        "last_error": s.last_error,
    }


def _get_or_404(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    return source


@router.get("/sources")
def list_sources(db: Session = Depends(get_session)):
    return [_to_dict(s) for s in db.scalars(select(Source).order_by(Source.id)).all()]


@router.post("/sources", status_code=201)
def create_source(
    body: SourceCreate, db: Session = Depends(get_session), _=Depends(get_current_admin)
):
    if body.type not in ("rss", "webpage"):
        raise HTTPException(status_code=422, detail="自定义源类型仅支持 rss 或 webpage")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="URL 必须以 http(s):// 开头")
    source = Source(name=body.name.strip(), type=body.type, url=body.url.strip())
    db.add(source)
    db.commit()
    return _to_dict(source)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: int, body: SourcePatch,
    db: Session = Depends(get_session), _=Depends(get_current_admin),
):
    source = _get_or_404(db, source_id)
    if body.name is not None:
        source.name = body.name.strip()
    if body.url is not None:
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="URL 必须以 http(s):// 开头")
        source.url = body.url.strip()
    if body.enabled is not None:
        source.enabled = body.enabled
    db.commit()
    return _to_dict(source)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(
    source_id: int, db: Session = Depends(get_session), _=Depends(get_current_admin)
):
    source = _get_or_404(db, source_id)
    if source.is_builtin:
        raise HTTPException(status_code=400, detail="内置源不可删除，只能停用")
    db.delete(source)  # cascade 删除其 notices
    db.commit()


@router.post("/sources/{source_id}/fetch")
def fetch_now(
    source_id: int, db: Session = Depends(get_session), _=Depends(get_current_admin)
):
    source = _get_or_404(db, source_id)
    new_items = pipeline.fetch_source(db, source)
    notified = pipeline.send_pending(db)
    return {"new_items": new_items, "notified": notified,
            "last_fetch_status": source.last_fetch_status, "last_error": source.last_error}
