from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class DocumentMetadata(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)

    # PDF metadata
    title = Column(String(500))
    author = Column(String(255))
    pdf_created_at = Column(DateTime)

    # Content stats
    page_count = Column(Integer, default=0)
    word_count = Column(Integer, default=0)
    char_count = Column(Integer, default=0)
    file_size = Column(Integer, default=0)

    # Extracted content
    extracted_text = Column(Text)

    # PII and entities
    emails_found = Column(Text)
    phone_numbers_found = Column(Text)
    urls_found = Column(Text)
    dates_found = Column(Text)
    pii_found = Column(Boolean, default=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
