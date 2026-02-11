from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float

from user_service.core.database import Base


class InstructorProfile(Base):
    """Instructor profile extending User model."""
    __tablename__ = "instructor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Profile information
    bio = Column(Text, nullable=True)
    expertise = Column(String(500), nullable=True)  # Comma-separated or JSON array of subjects
    profile_picture_url = Column(String(500), nullable=True)
    phone_number = Column(String(20), nullable=True)
    
    # Statistics
    total_students = Column(Integer, default=0, nullable=False)
    total_courses = Column(Integer, default=0, nullable=False)
    average_rating = Column(Float, default=0.0, nullable=False)
    
    # Verification
    is_verified_instructor = Column(Integer, default=False, nullable=False)
    verification_date = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<InstructorProfile(user_id={self.user_id}, total_courses={self.total_courses})>"
