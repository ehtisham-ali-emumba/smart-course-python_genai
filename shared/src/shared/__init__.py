"""Shared library for SmartCourse microservices."""

# Keep package init lightweight and side-effect free.
# Subpackages are imported directly by services as needed.
__all__ = ["kafka", "schemas", "exceptions", "utils"]
