from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PIIResult(BaseModel):
    emails: List[str]
    phone_numbers: List[str]
    pii_found: bool


class DocumentMetadataBase(BaseModel):
    filename: str
    extracted_text: Optional[str] = None


class DocumentMetadataCreate(DocumentMetadataBase):
    emails_found: List[str] = []
    phone_numbers_found: List[str] = []
    pii_found: bool = False


class DocumentMetadataResponse(DocumentMetadataBase):
    id: int
    emails_found: List[str]
    phone_numbers_found: List[str]
    pii_found: bool
    created_at: datetime

    class Config:
        from_attributes = True
