"""
Configuration settings for eCourts Cause List Scraper using Pydantic Settings.

This module provides centralized configuration management with environment variable
support and validation for the eCourts Cause List Scraper application.
"""

import os
from pathlib import Path
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application metadata
    app_name: str = Field(default="eCourts Cause List Scraper", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode flag")
    
    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host address")
    port: int = Field(default=8000, description="Server port number")
    
    # eCourts portal URLs
    ecourts_base_url: str = Field(
        default="https://ecourts.gov.in", 
        description="Base URL for eCourts portal"
    )
    ecourts_services_url: str = Field(
        default="https://ecourts.gov.in/ecourts_home/static/manuals/cis/",
        description="eCourts services URL for dropdown data"
    )
    ecourts_causelist_url: str = Field(
        default="https://ecourts.gov.in/ecourts_home/static/causelist/",
        description="eCourts cause list URL for PDF downloads"
    )
    
    # File handling settings
    max_file_size: int = Field(
        default=50 * 1024 * 1024,  # 50MB
        description="Maximum file size for downloads in bytes"
    )
    allowed_file_types: List[str] = Field(
        default=[".pdf"],
        description="List of allowed file extensions"
    )
    
    # Request timeout and retry settings
    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts for failed requests"
    )
    retry_delay: float = Field(
        default=1.0,
        description="Delay between retry attempts in seconds"
    )
    
    # Session and caching settings
    session_timeout: int = Field(
        default=3600,  # 1 hour
        description="Session timeout for cached data in seconds"
    )
    enable_caching: bool = Field(
        default=True,
        description="Enable caching of dropdown data"
    )
    
    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_file: str = Field(
        default="ecourts_scraper.log",
        description="Log file name"
    )
    
    # Mock mode settings
    mock_mode: bool = Field(
        default=True,
        description="Enable mock mode when eCourts portal is unavailable"
    )
    realistic_mock_data: bool = Field(
        default=True,
        description="Generate realistic mock cause list data instead of simple placeholders"
    )
    
    # Security settings
    cors_origins: List[str] = Field(
        default=["*"],
        description="CORS allowed origins"
    )
    cors_methods: List[str] = Field(
        default=["GET", "POST"],
        description="CORS allowed methods"
    )
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        """Validate port number is within valid range."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator('max_file_size')
    @classmethod
    def validate_max_file_size(cls, v):
        """Validate max file size is positive."""
        if v <= 0:
            raise ValueError("Max file size must be positive")
        return v
    
    @field_validator('request_timeout', 'max_retries')
    @classmethod
    def validate_positive_integers(cls, v):
        """Validate positive integer fields."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v
    
    @field_validator('retry_delay')
    @classmethod
    def validate_retry_delay(cls, v):
        """Validate retry delay is non-negative."""
        if v < 0:
            raise ValueError("Retry delay must be non-negative")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level is valid."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.upper()
    
    @field_validator('ecourts_base_url', 'ecourts_services_url', 'ecourts_causelist_url')
    @classmethod
    def validate_urls(cls, v):
        """Validate URLs start with http or https."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URLs must start with http:// or https://")
        return v
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Convert environment variable names from UPPER_CASE to lower_case
        env_prefix = "ECOURTS_"


# Create settings instance
settings = Settings()

# Directory configuration (computed from settings)
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DOWNLOADS_DIR = STATIC_DIR / "downloads"
IMAGES_DIR = STATIC_DIR / "images"
TEMPLATES_DIR = BASE_DIR / "templates"
CSS_DIR = STATIC_DIR / "css"

# Ensure directories exist
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
CSS_DIR.mkdir(parents=True, exist_ok=True)

# Export commonly used settings for backward compatibility
APP_NAME = settings.app_name
APP_VERSION = settings.app_version
DEBUG = settings.debug
HOST = settings.host
PORT = settings.port
ECOURTS_BASE_URL = settings.ecourts_base_url
MAX_FILE_SIZE = settings.max_file_size
ALLOWED_FILE_TYPES = settings.allowed_file_types
REQUEST_TIMEOUT = settings.request_timeout
MAX_RETRIES = settings.max_retries