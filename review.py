from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import ReviewRecord

router = APIRouter(prefix="/review", tags=["review"])


@router.get("")
def list_reviews(limit: int = 100, database: Session = Depends(get_db)):
    rows = database.scalars(select(ReviewRecord).where(ReviewRecord.deleted.is_(False)).order_by(ReviewRecord.updated_at.desc()).limit(min(max(limit, 1), 500))).all()
    return [{"id": row.id, "updated_at": row.updated_at, "data": row.payload} for row in rows]
