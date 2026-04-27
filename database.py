# -*- coding: utf-8 -*-
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager
from datetime import datetime
import urllib.parse

# ─────────────────────────────────────────────
# DB 연결 설정 (비밀번호/서버주소 유지)
# ─────────────────────────────────────────────
DB_PASSWORD = urllib.parse.quote_plus("Ppooii**9098")
SQLALCHEMY_DATABASE_URL = f"postgresql://postgres:{DB_PASSWORD}@matching-db-2026.cozmuw2eq103.us-east-1.rds.amazonaws.com:5432/matching_db"

# 개선: pool_pre_ping → 죽은 연결 자동 감지/재연결 (AWS RDS 타임아웃 방지)
# 개선: pool_recycle=300 → 5분마다 연결 갱신 (스테일 커넥션 방지)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─────────────────────────────────────────────
# 모델 정의
# ─────────────────────────────────────────────
class MasterProduct(Base):
    __tablename__ = "master_products"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    product_name = Column(String, index=True)
    options = Column(String)
    wholesale_name = Column(String)
    supply_price = Column(Float)
    uploaded_at = Column(DateTime, nullable=True)


class Synonym(Base):
    __tablename__ = "synonyms"
    id = Column(Integer, primary_key=True, index=True)
    standard_word = Column(String, index=True)
    synonym_word = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    apply_brand = Column(Boolean, default=True)
    apply_product = Column(Boolean, default=True)
    apply_option = Column(Boolean, default=False)
    is_exact_match = Column(Boolean, default=False)


class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(Integer, primary_key=True, index=True)
    keyword_text = Column(String, unique=True, index=True)


# ─────────────────────────────────────────────
# 개선: init_db() - import 시 자동 실행 방지
# 앱 시작 시 명시적으로 한 번만 호출
# ─────────────────────────────────────────────
def init_db():
    """테이블이 없을 경우 생성. 앱 시작 시 한 번만 호출."""
    Base.metadata.create_all(bind=engine)
    # 기존 테이블에 uploaded_at 컬럼이 없을 경우 자동 추가 (마이그레이션)
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE master_products ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMP NULL"
        ))
        conn.commit()


# ─────────────────────────────────────────────
# 개선: get_db() - 컨텍스트 매니저로 세션 자동 관리
# with get_db() as db: 사용 시 예외 발생해도 자동으로 db.close() 보장
# ─────────────────────────────────────────────
@contextmanager
def get_db():
    """DB 세션 컨텍스트 매니저 - 예외 발생 시에도 세션 자동 닫힘."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
