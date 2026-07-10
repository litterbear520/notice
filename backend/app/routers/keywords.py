from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_session
from ..models import Keyword

router = APIRouter(prefix="/api")


class KeywordCreate(BaseModel):
    word: str


class KeywordPatch(BaseModel):
    enabled: bool


@router.get("/keywords")
def list_keywords(db: Session = Depends(get_session)):
    return [
        {"id": k.id, "word": k.word, "enabled": k.enabled}
        for k in db.scalars(select(Keyword).order_by(Keyword.id)).all()
    ]


@router.post("/keywords", status_code=201)
def create_keyword(
    body: KeywordCreate, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=422, detail="关键词不能为空")
    if db.scalars(select(Keyword).where(Keyword.word == word)).first():
        raise HTTPException(status_code=409, detail="关键词已存在")
    keyword = Keyword(word=word, enabled=True)
    db.add(keyword)
    db.commit()
    return {"id": keyword.id, "word": keyword.word, "enabled": keyword.enabled}


@router.patch("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int, body: KeywordPatch,
    db: Session = Depends(get_session), _=Depends(get_current_user),
):
    keyword = db.get(Keyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    keyword.enabled = body.enabled
    db.commit()
    return {"id": keyword.id, "word": keyword.word, "enabled": keyword.enabled}


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    keyword = db.get(Keyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    db.delete(keyword)
    db.commit()
