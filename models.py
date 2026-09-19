from sqlalchemy import BigInteger, Boolean, Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base


class SyncColumns:
    id = Column(String(128), primary_key=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False, index=True)
    sync_status = Column(String(32), nullable=False, default="SYNCED")
    deleted = Column(Boolean, nullable=False, default=False, index=True)


class User(Base, SyncColumns):
    __tablename__ = "users"
    display_name = Column(String(120), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)


class DailyTask(Base, SyncColumns):
    __tablename__ = "daily_tasks"
    payload = Column(JSONB, nullable=False, default=dict)


class ReviewRecord(Base, SyncColumns):
    __tablename__ = "review_records"
    mistake_id = Column(String(128), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)


class EssayReview(Base, SyncColumns):
    __tablename__ = "essay_reviews"
    essay_date = Column(BigInteger, nullable=True, index=True)
    title = Column(Text, nullable=True)
    essay_type = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)


class AIAnalysis(Base, SyncColumns):
    """AI 分析的可查询镜像；原始内容同时保存于通用 sync_entities。"""
    __tablename__ = "ai_analyses"
    analysis_type = Column(String(64), nullable=False, index=True)
    input_payload = Column(JSONB, nullable=False, default=dict)
    output_payload = Column(JSONB, nullable=False, default=dict)


class WrongQuestion(Base, SyncColumns):
    __tablename__ = "wrong_questions"
    module = Column(String(64), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)


class WrongQuestionImage(Base, SyncColumns):
    __tablename__ = "wrong_question_images"
    mistake_id = Column(String(128), nullable=True, index=True)
    image_path = Column(Text, nullable=True)
    image_hash = Column(String(128), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)


class Formula(Base, SyncColumns):
    __tablename__ = "formulas"
    category = Column(String(64), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)


class MemoryPractice(Base, SyncColumns):
    __tablename__ = "memory_practices"
    item_id = Column(String(128), nullable=True, index=True)
    practice_type = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)


class PercentPractice(Base, SyncColumns):
    __tablename__ = "percent_practices"
    item_id = Column(String(128), nullable=True, index=True)
    practice_type = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)


class SquarePractice(Base, SyncColumns):
    __tablename__ = "square_practices"
    item_id = Column(String(128), nullable=True, index=True)
    practice_type = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)


class StudyStatistic(Base, SyncColumns):
    __tablename__ = "study_statistics"
    statistic_date = Column(BigInteger, nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)


class SyncEntity(Base):
    """同步的权威通用存储；保留原始手机记录，避免服务端字段演进影响旧 App。"""
    __tablename__ = "sync_entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, default="local-user", index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(128), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False, index=True)
    deleted = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_sync_entity"),)


class SyncChange(Base):
    __tablename__ = "sync_changes"
    cursor = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, default="local-user", index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(BigInteger, nullable=False)
    deleted = Column(Boolean, nullable=False, default=False)
    source_device_id = Column(String(128), nullable=True)


class MediaObject(Base):
    __tablename__ = "media_objects"
    id = Column(String(128), primary_key=True)
    image_hash = Column(String(128), nullable=False, unique=True, index=True)
    image_path = Column(Text, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    sync_status = Column(String(32), nullable=False, default="SYNCED")
    deleted = Column(Boolean, nullable=False, default=False)
