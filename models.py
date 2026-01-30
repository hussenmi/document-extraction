from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PIIResult(BaseModel):
    emails: List[str]
    phone_numbers: List[str]
    urls: List[str]
    dates: List[str]
    pii_found: bool


class DocumentStats(BaseModel):
    total_documents: int
    documents_with_pii: int
    total_emails_found: int
    total_phone_numbers_found: int
    total_pages_processed: int


class DocumentMetadataBase(BaseModel):
    filename: str
    title: Optional[str] = None
    author: Optional[str] = None


class DocumentMetadataCreate(DocumentMetadataBase):
    pass


class DocumentMetadataResponse(BaseModel):
    id: int
    filename: str

    # PDF metadata
    title: Optional[str] = None
    author: Optional[str] = None
    pdf_created_at: Optional[datetime] = None

    # Content stats
    page_count: int
    word_count: int
    char_count: int
    file_size: int

    # Extracted content
    extracted_text: Optional[str] = None

    # PII and entities
    emails_found: List[str]
    phone_numbers_found: List[str]
    urls_found: List[str]
    dates_found: List[str]
    pii_found: bool

    # Timestamps
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    id: int
    filename: str
    title: Optional[str] = None
    author: Optional[str] = None
    page_count: int
    word_count: int
    file_size: int
    pii_found: bool
    emails_count: int
    phones_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    documents: List[DocumentListResponse]
    total: int
    query: Optional[str] = None
