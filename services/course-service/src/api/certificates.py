from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_instructor
from core.database import get_db
from schemas.certificate import (
    CertificateCreate,
    CertificateResponse,
    CertificateVerifyResponse,
)
from services.certificate import CertificateService

router = APIRouter()


@router.post("/", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def issue_certificate(
    data: CertificateCreate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Issue a certificate for a completed enrollment (instructors only)."""
    service = CertificateService(db)
    try:
        cert = await service.issue_certificate(data, instructor_id)
        return CertificateResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/verify/{verification_code}", response_model=CertificateVerifyResponse)
async def verify_certificate(
    verification_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to verify a certificate by its verification code."""
    service = CertificateService(db)
    cert = await service.verify_certificate(verification_code)
    if not cert:
        return CertificateVerifyResponse(is_valid=False)
    return CertificateVerifyResponse(
        is_valid=not cert.is_revoked,
        certificate_number=cert.certificate_number,
        issue_date=cert.issue_date,
        grade=cert.grade,
        is_revoked=cert.is_revoked,
    )


@router.get("/{certificate_id}", response_model=CertificateResponse)
async def get_certificate(
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a certificate by ID."""
    service = CertificateService(db)
    cert = await service.get_certificate(certificate_id)
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return CertificateResponse.model_validate(cert)
