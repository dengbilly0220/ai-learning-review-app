from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.formula import router as formula_router
from api.ai import router as ai_router
from api.upload import router as upload_router
from api.review import router as review_router
from api.statistics import router as statistics_router
from api.sync import router as sync_router
from api.wrong_question import router as wrong_question_router
from database.database import Base, engine, get_db
import database.models  # noqa: F401 - registers all PostgreSQL tables

app = FastAPI(title="公考复盘助手 NAS 同步服务", version="1.0.0")


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/ping")
def ping(database: Session = Depends(get_db)) -> dict[str, str]:
    database.execute(text("SELECT 1"))
    return {"status": "ok", "service": "gongkao-nas-sync"}


app.include_router(sync_router)
app.include_router(wrong_question_router)
app.include_router(review_router)
app.include_router(formula_router)
app.include_router(statistics_router)
app.include_router(ai_router)
app.include_router(upload_router)
