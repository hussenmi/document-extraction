import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import engine, get_db, Base, DocumentMetadata
from models import DocumentMetadataResponse, DocumentListResponse, DocumentStats, SearchResult

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PDF Document Management API", version="2.0.0")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# --- Extraction Functions ---

def extract_text_from_pdf(file_content: bytes) -> dict:
    """Extract text and metadata from PDF."""
    pdf_file = BytesIO(file_content)
    reader = PdfReader(pdf_file)

    # Extract text from all pages
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""

    # Extract PDF metadata
    metadata = reader.metadata or {}

    # Parse PDF creation date
    pdf_created = None
    if metadata.get("/CreationDate"):
        try:
            date_str = metadata["/CreationDate"]
            # PDF date format: D:YYYYMMDDHHmmSS
            if date_str.startswith("D:"):
                date_str = date_str[2:16]
                pdf_created = datetime.strptime(date_str, "%Y%m%d%H%M%S")
        except (ValueError, IndexError):
            pass

    return {
        "text": text,
        "page_count": len(reader.pages),
        "title": metadata.get("/Title"),
        "author": metadata.get("/Author"),
        "pdf_created_at": pdf_created,
    }


def extract_entities(text: str) -> dict:
    """Extract PII and other entities from text."""
    # Email pattern
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails = list(set(re.findall(email_pattern, text)))

    # Phone pattern
    phone_pattern = r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    phone_numbers = list(set(re.findall(phone_pattern, text)))

    # URL pattern
    url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
    urls = list(set(re.findall(url_pattern, text)))

    # Date pattern (various formats)
    date_pattern = r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b"
    dates = list(set(re.findall(date_pattern, text, re.IGNORECASE)))

    return {
        "emails": emails,
        "phone_numbers": phone_numbers,
        "urls": urls,
        "dates": dates,
        "pii_found": len(emails) > 0 or len(phone_numbers) > 0
    }


def compute_content_stats(text: str) -> dict:
    """Compute content statistics."""
    words = text.split()
    return {
        "word_count": len(words),
        "char_count": len(text)
    }


# --- Helper Functions ---

def parse_list(value: str) -> List[str]:
    """Parse comma-separated string to list."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def to_list_response(doc: DocumentMetadata) -> DocumentListResponse:
    """Convert database model to list response."""
    emails = parse_list(doc.emails_found)
    phones = parse_list(doc.phone_numbers_found)
    return DocumentListResponse(
        id=doc.id,
        filename=doc.filename,
        title=doc.title,
        author=doc.author,
        page_count=doc.page_count,
        word_count=doc.word_count,
        file_size=doc.file_size,
        pii_found=doc.pii_found,
        emails_count=len(emails),
        phones_count=len(phones),
        created_at=doc.created_at
    )


def to_full_response(doc: DocumentMetadata) -> DocumentMetadataResponse:
    """Convert database model to full response."""
    return DocumentMetadataResponse(
        id=doc.id,
        filename=doc.filename,
        title=doc.title,
        author=doc.author,
        pdf_created_at=doc.pdf_created_at,
        page_count=doc.page_count,
        word_count=doc.word_count,
        char_count=doc.char_count,
        file_size=doc.file_size,
        extracted_text=doc.extracted_text,
        emails_found=parse_list(doc.emails_found),
        phone_numbers_found=parse_list(doc.phone_numbers_found),
        urls_found=parse_list(doc.urls_found),
        dates_found=parse_list(doc.dates_found),
        pii_found=doc.pii_found,
        created_at=doc.created_at
    )


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/stats", response_model=DocumentStats)
def get_stats(db: Session = Depends(get_db)):
    """Get aggregate statistics for all documents."""
    documents = db.query(DocumentMetadata).all()

    total_emails = 0
    total_phones = 0
    total_pages = 0
    pii_count = 0

    for doc in documents:
        total_emails += len(parse_list(doc.emails_found))
        total_phones += len(parse_list(doc.phone_numbers_found))
        total_pages += doc.page_count or 0
        if doc.pii_found:
            pii_count += 1

    return DocumentStats(
        total_documents=len(documents),
        documents_with_pii=pii_count,
        total_emails_found=total_emails,
        total_phone_numbers_found=total_phones,
        total_pages_processed=total_pages
    )


@app.post("/upload", response_model=DocumentMetadataResponse)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and process a PDF document."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    file_size = len(content)

    # Extract PDF content and metadata
    pdf_data = extract_text_from_pdf(content)
    entities = extract_entities(pdf_data["text"])
    stats = compute_content_stats(pdf_data["text"])

    # Create document record
    document = DocumentMetadata(
        filename=file.filename,
        title=pdf_data["title"],
        author=pdf_data["author"],
        pdf_created_at=pdf_data["pdf_created_at"],
        page_count=pdf_data["page_count"],
        word_count=stats["word_count"],
        char_count=stats["char_count"],
        file_size=file_size,
        extracted_text=pdf_data["text"],
        emails_found=",".join(entities["emails"]),
        phone_numbers_found=",".join(entities["phone_numbers"]),
        urls_found=",".join(entities["urls"]),
        dates_found=",".join(entities["dates"]),
        pii_found=entities["pii_found"]
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return to_full_response(document)


@app.get("/documents", response_model=SearchResult)
def get_documents(
    pii_found: Optional[bool] = Query(None, description="Filter by PII presence"),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    author: Optional[str] = Query(None, description="Filter by author"),
    limit: int = Query(100, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Skip results"),
    db: Session = Depends(get_db)
):
    """List documents with optional filters."""
    query = db.query(DocumentMetadata)

    if pii_found is not None:
        query = query.filter(DocumentMetadata.pii_found == pii_found)

    if from_date:
        query = query.filter(DocumentMetadata.created_at >= from_date)

    if to_date:
        query = query.filter(DocumentMetadata.created_at <= to_date)

    if author:
        query = query.filter(DocumentMetadata.author.ilike(f"%{author}%"))

    total = query.count()
    documents = query.order_by(DocumentMetadata.created_at.desc()).offset(offset).limit(limit).all()

    return SearchResult(
        documents=[to_list_response(doc) for doc in documents],
        total=total
    )


@app.get("/documents/search", response_model=SearchResult)
def search_documents(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(100, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Skip results"),
    db: Session = Depends(get_db)
):
    """Full-text search in document content and metadata."""
    search_term = f"%{q}%"

    query = db.query(DocumentMetadata).filter(
        or_(
            DocumentMetadata.extracted_text.ilike(search_term),
            DocumentMetadata.filename.ilike(search_term),
            DocumentMetadata.title.ilike(search_term),
            DocumentMetadata.author.ilike(search_term)
        )
    )

    total = query.count()
    documents = query.order_by(DocumentMetadata.created_at.desc()).offset(offset).limit(limit).all()

    return SearchResult(
        documents=[to_list_response(doc) for doc in documents],
        total=total,
        query=q
    )


@app.get("/documents/{document_id}", response_model=DocumentMetadataResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get a single document by ID."""
    document = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return to_full_response(document)


@app.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete a document by ID."""
    document = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully", "id": document_id}
