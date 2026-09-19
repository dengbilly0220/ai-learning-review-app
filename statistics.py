from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import SyncEntity, WrongQuestion

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/summary")
def summary(database: Session = Depends(get_db)):
    total = database.scalar(select(func.count()).select_from(SyncEntity).where(SyncEntity.deleted.is_(False))) or 0
    mistakes = database.scalar(select(func.count()).select_from(WrongQuestion).where(WrongQuestion.deleted.is_(False))) or 0
    return {"synced_records": total, "wrong_questions": mistakes}
