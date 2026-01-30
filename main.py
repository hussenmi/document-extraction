import re
from io import BytesIO
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session

from database import engine, get_db, Base, DocumentMetadata
from models import DocumentMetadataResponse

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FastAPI App", version="1.0.0")


def extract_text_from_pdf(file_content: bytes) -> str:
    pdf_file = BytesIO(file_content)
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def detect_pii(text: str) -> dict:
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    phone_pattern = r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"

    emails = re.findall(email_pattern, text)
    phone_numbers = re.findall(phone_pattern, text)

    return {
        "emails": list(set(emails)),
        "phone_numbers": list(set(phone_numbers)),
        "pii_found": len(emails) > 0 or len(phone_numbers) > 0
    }


@app.get("/")
def root():
    return {"message": "Welcome to FastAPI"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/upload", response_model=DocumentMetadataResponse)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    extracted_text = extract_text_from_pdf(content)
    pii_results = detect_pii(extracted_text)

    document = DocumentMetadata(
        filename=file.filename,
        extracted_text=extracted_text,
        emails_found=",".join(pii_results["emails"]),
        phone_numbers_found=",".join(pii_results["phone_numbers"]),
        pii_found=pii_results["pii_found"]
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return DocumentMetadataResponse(
        id=document.id,
        filename=document.filename,
        extracted_text=document.extracted_text,
        emails_found=document.emails_found.split(",") if document.emails_found else [],
        phone_numbers_found=document.phone_numbers_found.split(",") if document.phone_numbers_found else [],
        pii_found=document.pii_found,
        created_at=document.created_at
    )


@app.get("/documents", response_model=List[DocumentMetadataResponse])
def get_documents(db: Session = Depends(get_db)):
    documents = db.query(DocumentMetadata).all()
    return [
        DocumentMetadataResponse(
            id=doc.id,
            filename=doc.filename,
            extracted_text=doc.extracted_text,
            emails_found=doc.emails_found.split(",") if doc.emails_found else [],
            phone_numbers_found=doc.phone_numbers_found.split(",") if doc.phone_numbers_found else [],
            pii_found=doc.pii_found,
            created_at=doc.created_at
        )
        for doc in documents
    ]
