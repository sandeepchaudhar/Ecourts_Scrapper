"""
Pydantic models for eCourts Cause List Scraper.

This module contains data models for court hierarchy, download requests,
results, and error responses with proper validation.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import re


class CourtHierarchy(BaseModel):
    """Model representing the court hierarchy structure."""
    
    state_code: str = Field(..., description="State code from eCourts portal")
    state_name: str = Field(..., description="State name")
    district_code: Optional[str] = Field(None, description="District code from eCourts portal")
    district_name: Optional[str] = Field(None, description="District name")
    complex_code: Optional[str] = Field(None, description="Court complex code from eCourts portal")
    complex_name: Optional[str] = Field(None, description="Court complex name")
    court_code: Optional[str] = Field(None, description="Individual court code from eCourts portal")
    court_name: Optional[str] = Field(None, description="Individual court name")

    @field_validator('state_code', 'district_code', 'complex_code', 'court_code')
    @classmethod
    def validate_codes(cls, v):
        """Validate that codes are non-empty strings when provided."""
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("Codes must be non-empty strings")
        return v.strip() if v else v

    @field_validator('state_name', 'district_name', 'complex_name', 'court_name')
    @classmethod
    def validate_names(cls, v):
        """Validate that names are non-empty strings when provided."""
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("Names must be non-empty strings")
        return v.strip() if v else v


class DownloadRequest(BaseModel):
    """Model for cause list download requests."""
    
    state_code: str = Field(..., description="State code for the court")
    district_code: str = Field(..., description="District code for the court")
    complex_code: str = Field(..., description="Court complex code")
    court_code: Optional[str] = Field(None, description="Specific court code (optional for bulk download)")
    date: str = Field(..., description="Date for cause list in YYYY-MM-DD format")

    @field_validator('state_code', 'district_code', 'complex_code')
    @classmethod
    def validate_required_codes(cls, v):
        """Validate required codes are non-empty strings."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Required codes must be non-empty strings")
        return v.strip()

    @field_validator('court_code')
    @classmethod
    def validate_court_code(cls, v):
        """Validate court code when provided."""
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("Court code must be a non-empty string when provided")
        return v.strip() if v else v

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, v):
        """Validate date format is YYYY-MM-DD."""
        if not isinstance(v, str):
            raise ValueError("Date must be a string")
        
        # Check format using regex
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(date_pattern, v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        
        # Validate it's a real date
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Invalid date provided")
        
        return v


class DownloadResult(BaseModel):
    """Model for download operation results."""
    
    success: bool = Field(..., description="Whether the download was successful")
    filename: str = Field(..., description="Name of the downloaded file")
    file_size: int = Field(0, description="Size of the downloaded file in bytes")
    download_url: str = Field(..., description="URL to access the downloaded file")
    error_message: Optional[str] = Field(None, description="Error message if download failed")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the download was completed")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}

    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v):
        """Validate filename is not empty."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Filename must be a non-empty string")
        return v.strip()

    @field_validator('file_size')
    @classmethod
    def validate_file_size(cls, v):
        """Validate file size is non-negative."""
        if not isinstance(v, int) or v < 0:
            raise ValueError("File size must be a non-negative integer")
        return v

    @field_validator('download_url')
    @classmethod
    def validate_download_url(cls, v):
        """Validate download URL is not empty."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Download URL must be a non-empty string")
        return v.strip()


class ErrorResponse(BaseModel):
    """Model for error responses."""
    
    error: bool = Field(True, description="Always True for error responses")
    message: str = Field(..., description="Human-readable error message")
    error_code: str = Field(..., description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the error occurred")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}

    @field_validator('message', 'error_code')
    @classmethod
    def validate_required_strings(cls, v):
        """Validate required string fields are not empty."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Required string fields must be non-empty")
        return v.strip()


class BulkDownloadRequest(BaseModel):
    """Model for bulk download requests (when only complex is selected)."""
    
    state_code: str = Field(..., description="State code for the courts")
    district_code: str = Field(..., description="District code for the courts")
    complex_code: str = Field(..., description="Court complex code")
    date: str = Field(..., description="Date for cause lists in YYYY-MM-DD format")

    @field_validator('state_code', 'district_code', 'complex_code')
    @classmethod
    def validate_required_codes(cls, v):
        """Validate required codes are non-empty strings."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Required codes must be non-empty strings")
        return v.strip()

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, v):
        """Validate date format is YYYY-MM-DD."""
        if not isinstance(v, str):
            raise ValueError("Date must be a string")
        
        # Check format using regex
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(date_pattern, v):
            raise ValueError("Date must be in YYYY-MM-DD format")
        
        # Validate it's a real date
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Invalid date provided")
        
        return v


class BulkDownloadResult(BaseModel):
    """Model for bulk download operation results."""
    
    success: bool = Field(..., description="Whether the bulk download was successful")
    total_files: int = Field(..., description="Total number of files in the bulk download")
    successful_downloads: int = Field(..., description="Number of successful downloads")
    failed_downloads: int = Field(..., description="Number of failed downloads")
    download_results: List[DownloadResult] = Field(..., description="Individual download results")
    zip_filename: Optional[str] = Field(None, description="Name of the ZIP file containing all downloads")
    zip_download_url: Optional[str] = Field(None, description="URL to download the ZIP file")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the bulk download was completed")

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}

    @field_validator('total_files', 'successful_downloads', 'failed_downloads')
    @classmethod
    def validate_counts(cls, v):
        """Validate counts are non-negative integers."""
        if not isinstance(v, int) or v < 0:
            raise ValueError("Counts must be non-negative integers")
        return v

    @field_validator('zip_filename')
    @classmethod
    def validate_zip_filename(cls, v):
        """Validate ZIP filename when provided."""
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("ZIP filename must be a non-empty string when provided")
        return v.strip() if v else v

    @field_validator('zip_download_url')
    @classmethod
    def validate_zip_download_url(cls, v):
        """Validate ZIP download URL when provided."""
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ValueError("ZIP download URL must be a non-empty string when provided")
        return v.strip() if v else v