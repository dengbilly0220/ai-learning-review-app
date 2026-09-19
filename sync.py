"""Offline-first sync endpoints.

The phone remains the primary working database.  This module only stores a
versioned mirror and returns changes newer than a cursor.  Payloads are kept as
JSON so a newer mobile schema does not break an older NAS service.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    AIAnalysis, DailyTask, EssayReview, Formula, MemoryPractice, PercentPractice, ReviewRecord, SquarePractice,
    SyncChange, SyncEntity, User, WrongQuestion, WrongQuestionImage,
)

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncRecordIn(BaseModel):
    entity_type: str = Field(min_length=1, max_length=64)
    id: str = Field(min_length=1, max_length=128)
    operation: str = "UPSERT"
    updated_at: int
    deleted: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class UploadRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    user_id: str = "local-user"
    records: list[SyncRecordIn] = Field(default_factory=list, max_length=200)


MIRROR_MODELS = {
    "USER": User,
    "DAILY_TASK": DailyTask,
    "REVIEW": ReviewRecord,
    "ESSAY_REVIEW": EssayReview,
    "AI_ANALYSIS": AIAnalysis,
    "MISTAKE": WrongQuestion,
    "MISTAKE_IMAGE": WrongQuestionImage,
    "FORMULA": Formula,
    "MEMORY_PRACTICE": MemoryPractice,
}


def _created_at(record: SyncRecordIn) -> int:
    value = record.data.get("created_at", record.updated_at)
    return int(value) if isinstance(value, (int, float, str)) else record.updated_at


def _mirror_record(database: Session, record: SyncRecordIn) -> None:
    """Maintain readable PostgreSQL tables in addition to generic sync data."""
    model = MIRROR_MODELS.get(record.entity_type)
    if record.entity_type == "MEMORY_PRACTICE":
        if record.data.get("memory_type") == "PERCENT_FRACTION":
            model = PercentPractice
        elif record.data.get("memory_type") == "SQUARE":
            model = SquarePractice
    if model is None:
        return
    row = database.get(model, record.id)
    values: dict[str, Any] = {
        "id": record.id,
        "created_at": _created_at(record),
        "updated_at": record.updated_at,
        "sync_status": "SYNCED",
        "deleted": record.deleted,
    }
    # AIAnalysis 使用 input_payload/output_payload 两个明确字段，其他镜像表保留原始 payload。
    if model is not AIAnalysis:
        values["payload"] = record.data
    if model is User:
        values["display_name"] = record.data.get("display_name")
    elif model is ReviewRecord:
        values["mistake_id"] = record.data.get("mistake_id")
    elif model is EssayReview:
        values["essay_date"] = record.data.get("date")
        values["title"] = record.data.get("title")
        values["essay_type"] = record.data.get("essay_type")
    elif model is AIAnalysis:
        values["analysis_type"] = record.data.get("analysis_type", "unknown")
        values["input_payload"] = _json_value(record.data.get("input_json"))
        values["output_payload"] = _json_value(record.data.get("output_json"))
    elif model is WrongQuestion:
        values["module"] = record.data.get("module")
    elif model is WrongQuestionImage:
        values["mistake_id"] = record.data.get("mistake_id")
        values["image_path"] = record.data.get("remote_path") or record.data.get("image_path")
        values["image_hash"] = record.data.get("image_hash")
    elif model is Formula:
        values["category"] = record.data.get("category")
    elif model in {MemoryPractice, PercentPractice, SquarePractice}:
        values["item_id"] = record.data.get("memory_item_id")
        values["practice_type"] = record.data.get("memory_type")
    if row is None:
        database.add(model(**values))
    else:
        for key, value in values.items():
            setattr(row, key, value)


def _json_value(value: Any) -> dict[str, Any]:
    """SQLite 同步包中的 JSON 字段可能是字符串，也可能已被客户端解析。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = __import__("json").loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except ValueError:
            return {"raw": value}
    return {}


@router.post("/upload")
def upload_changes(body: UploadRequest, database: Session = Depends(get_db)) -> dict[str, Any]:
    accepted: list[str] = []
    skipped: list[str] = []
    latest: list[dict[str, Any]] = []
    for record in body.records:
        existing = database.scalar(select(SyncEntity).where(
            SyncEntity.user_id == body.user_id,
            SyncEntity.entity_type == record.entity_type,
            SyncEntity.entity_id == record.id,
        ))
        if existing is not None and existing.updated_at > record.updated_at:
            skipped.append(record.id)
            latest.append({
                "entityType": existing.entity_type,
                "entityId": existing.entity_id,
                "updatedAt": existing.updated_at,
                "deleted": existing.deleted,
                "data": existing.payload,
            })
            continue
        if existing is not None and existing.updated_at == record.updated_at and existing.deleted == record.deleted and existing.payload == record.data:
            skipped.append(record.id)
            continue
        if existing is None:
            existing = SyncEntity(
                user_id=body.user_id, entity_type=record.entity_type, entity_id=record.id,
                payload=record.data, created_at=_created_at(record), updated_at=record.updated_at,
                deleted=record.deleted,
            )
            database.add(existing)
        else:
            existing.payload = record.data
            existing.updated_at = record.updated_at
            existing.deleted = record.deleted
        _mirror_record(database, record)
        database.add(SyncChange(
            user_id=body.user_id, entity_type=record.entity_type, entity_id=record.id,
            payload=record.data, updated_at=record.updated_at, deleted=record.deleted,
            source_device_id=body.device_id,
        ))
        accepted.append(record.id)
    database.commit()
    return {"accepted": accepted, "skipped": skipped, "latest": latest}


@router.get("/download")
def download_changes(since: int = 0, device_id: str = "", user_id: str = "local-user", database: Session = Depends(get_db)) -> dict[str, Any]:
    changes = database.scalars(
        select(SyncChange)
        .where(SyncChange.user_id == user_id, SyncChange.cursor > max(0, since))
        .order_by(SyncChange.cursor.asc())
        .limit(500)
    ).all()
    records = [{
        "entityType": change.entity_type,
        "entityId": change.entity_id,
        "updatedAt": change.updated_at,
        "deleted": change.deleted,
        "data": change.payload,
    } for change in changes]
    cursor = changes[-1].cursor if changes else max(0, since)
    return {"cursor": cursor, "records": records, "device_id": device_id}
