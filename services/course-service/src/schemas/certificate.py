from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CertificateCreate(BaseModel):
    """Schema for issuing a certificate."""
    enrollment_id: int
    grade: Optional[str] = Field(None, max_length=10)
    score_percentage: Optional[Decimal] = Field(None, ge=0, le=100)


class CertificateResponse(BaseModel):
    """Schema for certificate API responses."""
    id: int
    enrollment_id: int
    certificate_number: str
    issue_date: date
    certificate_url: Optional[str]
    verification_code: str
    grade: Optional[str]
    score_percentage: Optional[Decimal]
    issued_by_id: Optional[int]
    is_revoked: bool
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CertificateVerifyResponse(BaseModel):
    """Schema for public certificate verification."""
    is_valid: bool
    certificate_number: Optional[str] = None
    issue_date: Optional[date] = None
    grade: Optional[str] = None
    is_revoked: bool = False


class CertificateListResponse(BaseModel):
    """Schema for listing certificates."""
    items: list[CertificateResponse]
    total: int
    skip: int
    limit: int
