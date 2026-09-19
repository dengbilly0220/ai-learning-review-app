from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Formula

router = APIRouter(prefix="/formula", tags=["formula"])


@router.get("")
def list_formulas(category: str | None = None, database: Session = Depends(get_db)):
    query = select(Formula).where(Formula.deleted.is_(False))
    if category:
        query = query.where(Formula.category == category)
    rows = database.scalars(query.order_by(Formula.updated_at.desc()).limit(500)).all()
    return [{"id": row.id, "category": row.category, "updated_at": row.updated_at, "data": row.payload} for row in rows]
