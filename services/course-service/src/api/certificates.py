from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_authenticated_user
from core.database import get_db
from schemas.certificate import (
    CertificateCreate,
    CertificateListResponse,
    CertificateResponse,
    CertificateVerifyResponse,
)
from services.certificate import CertificateService

router = APIRouter()


@router.post("/", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def issue_certificate(
    data: CertificateCreate,
    user: tuple[int, str] = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Request/issue a certificate for a completed enrollment.
    - Students: call this when all modules are complete; backend verifies completion and issues cert.
    - Instructors: can issue for any completed enrollment.
    """
    user_id, role = user
    service = CertificateService(db)
    try:
        cert = await service.issue_certificate(data, user_id, role)
        return CertificateResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my", response_model=CertificateListResponse)
async def list_my_certificates(
    skip: int = 0,
    limit: int = 50,
    user: tuple[int, str] = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all certificates for the current user."""
    user_id, role = user
    service = CertificateService(db)
    certs, total = await service.get_certificates_for_user(user_id, role, skip=skip, limit=limit)
    return CertificateListResponse(
        items=[CertificateResponse.model_validate(c) for c in certs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/enrollment/{enrollment_id}", response_model=CertificateResponse)
async def get_certificate_by_enrollment(
    enrollment_id: int,
    user: tuple[int, str] = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """Get certificate for a specific enrollment. Students can only access their own."""
    user_id, role = user
    service = CertificateService(db)
    try:
        cert = await service.get_certificate_by_enrollment(enrollment_id, user_id, role)
        return CertificateResponse.model_validate(cert)
    except ValueError as e:
        if "not found" in str(e).lower() or "no certificate" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


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
