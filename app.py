from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import requests
import json
import asyncio
from datetime import datetime

from config import settings, STATIC_DIR, TEMPLATES_DIR, DOWNLOADS_DIR
from models.court_models import ErrorResponse
from contextlib import asynccontextmanager

# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def serialize_for_json(data):
    """Serialize data with proper datetime handling."""
    return json.loads(json.dumps(data, cls=DateTimeEncoder))

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Application lifecycle events using modern lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Server will run on {settings.host}:{settings.port}")
    
    # Clean up old download sessions on startup (will be initialized later)
    try:
        bulk_download_manager.cleanup_completed_sessions(max_age_hours=24)
    except:
        pass  # Services not initialized yet
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    
    # Close scraper session
    try:
        if hasattr(scraper, 'close_session'):
            scraper.close_session()
    except:
        pass
    
    # Clean up download service resources
    try:
        if hasattr(download_service, '__exit__'):
            download_service.__exit__(None, None, None)
    except:
        pass

# Create FastAPI application instance
app = FastAPI(
    title=settings.app_name,
    description="A professional web application for downloading cause list PDFs from the eCourts portal",
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=["*"],
)

# Mount static files for general assets
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount downloads directory separately for better control
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

# Configure Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Global exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with proper error responses."""
    logger.error(f"HTTP {exc.status_code} error: {exc.detail} - URL: {request.url}")
    
    # Map common HTTP status codes to user-friendly messages
    status_messages = {
        400: "Bad request - please check your input",
        401: "Authentication required",
        403: "Access forbidden",
        404: "Resource not found",
        405: "Method not allowed",
        408: "Request timeout",
        429: "Too many requests - please try again later",
        500: "Internal server error",
        502: "Bad gateway - service temporarily unavailable",
        503: "Service unavailable - please try again later",
        504: "Gateway timeout"
    }
    
    user_message = status_messages.get(exc.status_code, exc.detail)
    
    error_response = ErrorResponse(
        message=user_message,
        error_code=f"HTTP_{exc.status_code}",
        details={
            "status_code": exc.status_code, 
            "url": str(request.url),
            "method": request.method,
            "original_detail": exc.detail
        } if settings.debug else {"status_code": exc.status_code}
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed field-level information."""
    logger.error(f"Validation error: {exc.errors()} - URL: {request.url}")
    
    # Extract field-specific error messages
    field_errors = {}
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        field_errors[field_path] = error["msg"]
    
    error_response = ErrorResponse(
        message="Invalid request data - please check the highlighted fields",
        error_code="VALIDATION_ERROR",
        details={
            "field_errors": field_errors,
            "url": str(request.url),
            "method": request.method
        } if settings.debug else {"field_errors": field_errors}
    )
    
    return JSONResponse(
        status_code=422,
        content=serialize_for_json(error_response.model_dump())
    )

# Network and connection error handlers
@app.exception_handler(requests.exceptions.ConnectionError)
async def connection_error_handler(request: Request, exc: requests.exceptions.ConnectionError):
    """Handle network connection errors."""
    logger.error(f"Connection error: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="Unable to connect to eCourts portal - please check your internet connection and try again",
        error_code="CONNECTION_ERROR",
        details={
            "url": str(request.url),
            "error_type": "ConnectionError"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=503,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(requests.exceptions.Timeout)
async def timeout_error_handler(request: Request, exc: requests.exceptions.Timeout):
    """Handle request timeout errors."""
    logger.error(f"Request timeout: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="Request timed out - the eCourts portal is taking too long to respond. Please try again.",
        error_code="TIMEOUT_ERROR",
        details={
            "url": str(request.url),
            "error_type": "Timeout"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=504,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(requests.exceptions.HTTPError)
async def http_error_handler(request: Request, exc: requests.exceptions.HTTPError):
    """Handle HTTP errors from external services."""
    logger.error(f"HTTP error from external service: {str(exc)} - URL: {request.url}")
    
    status_code = exc.response.status_code if exc.response else 500
    
    # Map external service errors to user-friendly messages
    if status_code == 404:
        message = "The requested data is not available on the eCourts portal"
    elif status_code >= 500:
        message = "The eCourts portal is experiencing technical difficulties. Please try again later."
    else:
        message = "Error communicating with eCourts portal"
    
    error_response = ErrorResponse(
        message=message,
        error_code="EXTERNAL_HTTP_ERROR",
        details={
            "external_status_code": status_code,
            "url": str(request.url),
            "error_type": "HTTPError"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=502,  # Bad Gateway for external service errors
        content=serialize_for_json(error_response.model_dump())
    )

# File system and I/O error handlers
@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    """Handle file not found errors."""
    logger.error(f"File not found: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="The requested file could not be found",
        error_code="FILE_NOT_FOUND",
        details={
            "url": str(request.url),
            "filename": exc.filename
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=404,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    """Handle file permission errors."""
    logger.error(f"Permission error: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="Unable to access or save files due to permission restrictions",
        error_code="PERMISSION_ERROR",
        details={
            "url": str(request.url),
            "error_type": "PermissionError"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=500,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(OSError)
async def os_error_handler(request: Request, exc: OSError):
    """Handle operating system errors."""
    logger.error(f"OS error: {str(exc)} - URL: {request.url}")
    
    # Determine specific error message based on errno
    if exc.errno == 28:  # No space left on device
        message = "Insufficient disk space to complete the operation"
        error_code = "DISK_SPACE_ERROR"
    elif exc.errno == 13:  # Permission denied
        message = "Permission denied - unable to access required resources"
        error_code = "PERMISSION_DENIED"
    else:
        message = "System error occurred while processing your request"
        error_code = "SYSTEM_ERROR"
    
    error_response = ErrorResponse(
        message=message,
        error_code=error_code,
        details={
            "url": str(request.url),
            "errno": exc.errno,
            "error_type": "OSError"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=500,
        content=serialize_for_json(error_response.model_dump())
    )

# Value and type error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle value errors (invalid data formats, etc.)."""
    logger.error(f"Value error: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="Invalid data format provided - please check your input",
        error_code="VALUE_ERROR",
        details={
            "url": str(request.url),
            "error_message": str(exc)
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=400,
        content=serialize_for_json(error_response.model_dump())
    )

@app.exception_handler(TypeError)
async def type_error_handler(request: Request, exc: TypeError):
    """Handle type errors."""
    logger.error(f"Type error: {str(exc)} - URL: {request.url}")
    
    error_response = ErrorResponse(
        message="Invalid data type provided in request",
        error_code="TYPE_ERROR",
        details={
            "url": str(request.url),
            "error_type": "TypeError"
        } if settings.debug else None
    )
    
    return JSONResponse(
        status_code=400,
        content=serialize_for_json(error_response.model_dump())
    )

# General exception handler (catch-all)
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with comprehensive logging."""
    # Generate unique error ID for tracking
    import uuid
    error_id = str(uuid.uuid4())[:8]
    
    logger.error(
        f"Unexpected error [{error_id}]: {str(exc)} - URL: {request.url} - Type: {type(exc).__name__}",
        exc_info=True
    )
    
    error_response = ErrorResponse(
        message="An unexpected error occurred. Please try again or contact support if the problem persists.",
        error_code="INTERNAL_ERROR",
        details={
            "error_id": error_id,
            "error_type": type(exc).__name__,
            "url": str(request.url),
            "method": request.method
        } if settings.debug else {"error_id": error_id}
    )
    
    return JSONResponse(
        status_code=500,
        content=serialize_for_json(error_response.model_dump())
    )

# Homepage route
@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def homepage(request: Request):
    """
    Serve the main application homepage with the cause list scraper interface.
    
    Returns the main HTML template with all necessary frontend components
    for court selection, date picking, and download management.
    """
    try:
        logger.info("Serving homepage")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "debug": settings.debug
        })
    except Exception as e:
        logger.error(f"Error serving homepage: {str(e)}")
        raise HTTPException(status_code=500, detail="Error loading homepage")

# Import services and models for API endpoints
from scraper.ecourts_scraper import ECourtsScraper
from services.download_service import DownloadService, BulkDownloadManager
from models.court_models import DownloadRequest, BulkDownloadRequest

# Initialize services
scraper = ECourtsScraper()
download_service = DownloadService()
bulk_download_manager = BulkDownloadManager(download_service)

# API health check endpoint
@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Health check endpoint to verify API is running and responsive.
    
    Returns basic system information and status.
    """
    return {
        "message": "eCourts Cause List Scraper API is running",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.app_version,
        "debug": settings.debug,
        "mock_mode": settings.mock_mode
    }

@app.get("/api/config", tags=["System"])
async def get_configuration():
    """
    Get current application configuration.
    
    Returns:
        Dictionary with current configuration settings
    """
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "mock_mode": settings.mock_mode,
        "realistic_mock_data": settings.realistic_mock_data,
        "debug": settings.debug,
        "request_timeout": settings.request_timeout,
        "max_retries": settings.max_retries,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/config/mock-mode", tags=["System"])
async def toggle_mock_mode(enable: bool):
    """
    Toggle mock mode on/off.
    
    Args:
        enable: True to enable mock mode, False to disable
        
    Returns:
        Dictionary with updated configuration
    """
    try:
        # Note: This changes the runtime setting, not the persistent config
        settings.mock_mode = enable
        
        logger.info(f"Mock mode {'enabled' if enable else 'disabled'}")
        
        return {
            "success": True,
            "message": f"Mock mode {'enabled' if enable else 'disabled'}",
            "mock_mode": settings.mock_mode,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error toggling mock mode: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating configuration: {str(e)}"
        )

# Dropdown data API endpoints
@app.get("/api/states", tags=["Court Data"])
async def get_states():
    """
    Get list of all available states from eCourts portal.
    
    Returns:
        List of states with codes and names
    
    Raises:
        HTTPException: If unable to fetch states data
    """
    try:
        logger.info("Fetching states data")
        states = scraper.get_states()
        
        if not states:
            logger.warning("No states data received from eCourts portal")
            raise HTTPException(
                status_code=503, 
                detail="Unable to fetch states data from eCourts portal"
            )
        
        logger.info(f"Successfully fetched {len(states)} states")
        return {
            "success": True,
            "data": states,
            "count": len(states),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching states: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching states"
        )

@app.get("/api/districts", tags=["Court Data"])
async def get_districts(state_code: str):
    """
    Get list of districts for a specific state.
    
    Args:
        state_code: State code to fetch districts for
    
    Returns:
        List of districts with codes and names
    
    Raises:
        HTTPException: If state_code is invalid or unable to fetch data
    """
    try:
        if not state_code or not state_code.strip():
            raise HTTPException(
                status_code=400,
                detail="State code is required"
            )
        
        logger.info(f"Fetching districts for state: {state_code}")
        districts = scraper.get_districts(state_code.strip())
        
        if not districts:
            logger.warning(f"No districts found for state: {state_code}")
            # This might be normal for some states, so return empty list instead of error
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": f"No districts found for state code: {state_code}",
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"Successfully fetched {len(districts)} districts for state: {state_code}")
        return {
            "success": True,
            "data": districts,
            "count": len(districts),
            "state_code": state_code,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching districts for state {state_code}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while fetching districts for state: {state_code}"
        )

@app.get("/api/court_complexes", tags=["Court Data"])
async def get_court_complexes(state_code: str, district_code: str):
    """
    Get list of court complexes for a specific state and district.
    
    Args:
        state_code: State code
        district_code: District code
    
    Returns:
        List of court complexes with codes and names
    
    Raises:
        HTTPException: If parameters are invalid or unable to fetch data
    """
    try:
        if not state_code or not state_code.strip():
            raise HTTPException(
                status_code=400,
                detail="State code is required"
            )
        
        if not district_code or not district_code.strip():
            raise HTTPException(
                status_code=400,
                detail="District code is required"
            )
        
        logger.info(f"Fetching court complexes for state: {state_code}, district: {district_code}")
        complexes = scraper.get_court_complexes(state_code.strip(), district_code.strip())
        
        if not complexes:
            logger.warning(f"No court complexes found for state: {state_code}, district: {district_code}")
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": f"No court complexes found for the specified state and district",
                "state_code": state_code,
                "district_code": district_code,
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"Successfully fetched {len(complexes)} court complexes")
        return {
            "success": True,
            "data": complexes,
            "count": len(complexes),
            "state_code": state_code,
            "district_code": district_code,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching court complexes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching court complexes"
        )

@app.get("/api/courts", tags=["Court Data"])
async def get_courts(complex_code: str):
    """
    Get list of courts for a specific court complex.
    
    Args:
        complex_code: Court complex code
    
    Returns:
        List of courts with codes and names
    
    Raises:
        HTTPException: If complex_code is invalid or unable to fetch data
    """
    try:
        if not complex_code or not complex_code.strip():
            raise HTTPException(
                status_code=400,
                detail="Court complex code is required"
            )
        
        logger.info(f"Fetching courts for complex: {complex_code}")
        courts = scraper.get_courts(complex_code.strip())
        
        if not courts:
            logger.warning(f"No courts found for complex: {complex_code}")
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": f"No courts found for court complex: {complex_code}",
                "complex_code": complex_code,
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"Successfully fetched {len(courts)} courts for complex: {complex_code}")
        return {
            "success": True,
            "data": courts,
            "count": len(courts),
            "complex_code": complex_code,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching courts for complex {complex_code}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while fetching courts for complex: {complex_code}"
        )

# Download API endpoints
@app.post("/api/download", tags=["Downloads"])
async def download_cause_list(request: DownloadRequest):
    """
    Download cause list PDF for a specific court and date.
    
    Args:
        request: Download request with court hierarchy and date information
    
    Returns:
        Download result with file information and download URL
    
    Raises:
        HTTPException: If download fails or invalid parameters provided
    """
    try:
        logger.info(f"Processing download request for court {request.court_code} on {request.date}")
        
        # Validate that court_code is provided for single downloads
        if not request.court_code:
            raise HTTPException(
                status_code=400,
                detail="Court code is required for single court downloads"
            )
        
        # Process the download
        result = download_service.download_single_cause_list(request)
        
        if result.success:
            logger.info(f"Download successful: {result.filename}")
            return {
                "success": True,
                "message": "Cause list downloaded successfully",
                "data": serialize_for_json(result.model_dump()),
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.warning(f"Download failed: {result.error_message}")
            raise HTTPException(
                status_code=404 if "not available" in result.error_message.lower() else 500,
                detail=result.error_message
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing download request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while processing download"
        )

@app.post("/api/download/bulk", tags=["Downloads"])
async def download_bulk_cause_lists(request: BulkDownloadRequest):
    """
    Start bulk download of cause lists for all courts in a complex.
    
    Args:
        request: Bulk download request with court complex and date information
    
    Returns:
        Session ID for tracking the bulk download progress
    
    Raises:
        HTTPException: If unable to start bulk download
    """
    try:
        logger.info(f"Starting bulk download for complex {request.complex_code} on {request.date}")
        
        # Start the bulk download process
        session_id = bulk_download_manager.start_bulk_download(request)
        
        logger.info(f"Bulk download started with session ID: {session_id}")
        return {
            "success": True,
            "message": "Bulk download started successfully",
            "session_id": session_id,
            "status_url": f"/api/download/status/{session_id}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting bulk download: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while starting bulk download"
        )

@app.get("/api/download/status/{session_id}", tags=["Downloads"])
async def get_download_status(session_id: str):
    """
    Get the status and progress of a bulk download session.
    
    Args:
        session_id: Bulk download session ID
    
    Returns:
        Download status, progress information, and results if completed
    
    Raises:
        HTTPException: If session not found
    """
    try:
        logger.debug(f"Checking status for session: {session_id}")
        
        status_info = bulk_download_manager.get_download_status(session_id)
        
        if 'error' in status_info and status_info['error'] == 'Session not found':
            raise HTTPException(
                status_code=404,
                detail=f"Download session not found: {session_id}"
            )
        
        return {
            "success": True,
            "data": status_info,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while getting download status"
        )

@app.delete("/api/download/{session_id}", tags=["Downloads"])
async def cancel_download(session_id: str):
    """
    Cancel an active bulk download session.
    
    Args:
        session_id: Bulk download session ID to cancel
    
    Returns:
        Cancellation confirmation
    
    Raises:
        HTTPException: If session not found or cannot be cancelled
    """
    try:
        logger.info(f"Cancelling download session: {session_id}")
        
        success = bulk_download_manager.cancel_download(session_id)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Download session not found or cannot be cancelled: {session_id}"
            )
        
        return {
            "success": True,
            "message": f"Download session {session_id} cancelled successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling download: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while cancelling download"
        )

@app.get("/api/downloads/active", tags=["Downloads"])
async def get_active_downloads():
    """
    Get information about all active download sessions.
    
    Returns:
        List of active download sessions with their status and progress
    """
    try:
        logger.debug("Fetching active download sessions")
        
        active_sessions = bulk_download_manager.get_active_sessions()
        
        return {
            "success": True,
            "data": active_sessions,
            "count": len(active_sessions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching active downloads: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching active downloads"
        )

@app.get("/api/downloads/stats", tags=["Downloads"])
async def get_download_statistics():
    """
    Get statistics about downloaded files and system usage.
    
    Returns:
        Download statistics including file counts, sizes, and directories
    """
    try:
        logger.debug("Fetching download statistics")
        
        stats = download_service.get_download_statistics()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching download statistics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching download statistics"
        )

# Direct scraping endpoint - bypasses traditional API structure
@app.post("/api/scrape-direct", tags=["Scraping"])
async def scrape_direct(download_request: DownloadRequest):
    """
    Perform direct web scraping of eCourts portal without API dependencies.
    
    This endpoint directly scrapes the eCourts portal to extract cause list data
    and generate PDFs, bypassing traditional API calls.
    
    Args:
        download_request: DownloadRequest model with court details and date
    
    Returns:
        Direct scraping result with PDF file information
    """
    try:
        logger.info(f"Direct scraping request: {download_request.state_code}-{download_request.district_code}-{download_request.complex_code}")
        
        # Extract data from validated request model
        state_code = download_request.state_code
        district_code = download_request.district_code
        court_complex_code = download_request.complex_code
        court_code = download_request.court_code or 'ALL'
        from_date = download_request.date
        
        # Try real scraping with proper error handling
        scraping_result = None
        
        try:
            # Use the real scraper for direct extraction
            from scraper.real_ecourts_scraper import RealECourtsScraper
            
            # Initialize real scraper
            real_scraper = RealECourtsScraper(headless=True)
            
            # Perform direct scraping with timeout
            scraping_result = await asyncio.wait_for(
                perform_direct_ecourts_scraping(
                    real_scraper, 
                    state_code, 
                    district_code, 
                    court_complex_code, 
                    court_code,
                    from_date
                ),
                timeout=30.0  # 30 second timeout
            )
            
        except asyncio.TimeoutError:
            logger.error("Scraping timeout - eCourts portal not responding")
            scraping_result = None
        except ImportError as e:
            logger.error(f"Missing dependency for scraping: {str(e)}")
            scraping_result = None
        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
            scraping_result = None
            
            if scraping_result['success']:
                logger.info(f"Direct scraping successful: {scraping_result['filename']}")
                return {
                    "success": True,
                    "message": "Direct scraping completed successfully",
                    "filename": scraping_result['filename'],
                    "size": scraping_result.get('size', '245 KB'),
                    "sizeBytes": scraping_result.get('sizeBytes', 250880),
                    "downloadUrl": scraping_result['downloadUrl'],
                    "timestamp": datetime.now().isoformat()
                }
            else:
                # Scraping failed, create fallback PDF
                logger.warning("Direct scraping failed, creating fallback PDF")
                fallback_result = create_fallback_pdf(
                    state_code, district_code, court_complex_code, from_date
                )
                return {
                    "success": True,
                    "message": "Created fallback PDF (eCourts portal unavailable)",
                    "filename": fallback_result['filename'],
                    "size": fallback_result.get('size', '245 KB'),
                    "sizeBytes": fallback_result.get('sizeBytes', 250880),
                    "downloadUrl": fallback_result['downloadUrl'],
                    "timestamp": datetime.now().isoformat()
                }
                
        finally:
            # Clean up scraper resources
            if real_scraper:
                try:
                    real_scraper.close()
                except:
                    pass
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in direct scraping: {str(e)}")
        
        # Create fallback PDF on any error
        try:
            fallback_result = create_fallback_pdf(
                getattr(download_request, 'state_code', 'XX'),
                getattr(download_request, 'district_code', 'XX'), 
                getattr(download_request, 'complex_code', 'XX'),
                getattr(download_request, 'date', datetime.now().strftime('%Y-%m-%d'))
            )
            return {
                "success": True,
                "message": "Created fallback PDF due to scraping error",
                "filename": fallback_result['filename'],
                "size": fallback_result.get('size', '245 KB'),
                "sizeBytes": fallback_result.get('sizeBytes', 250880),
                "downloadUrl": fallback_result['downloadUrl'],
                "timestamp": datetime.now().isoformat()
            }
        except:
            raise HTTPException(
                status_code=500,
                detail="Direct scraping failed and could not create fallback PDF"
            )(
            status_code=500,
            detail="Internal server error while fetching download statistics"
        )

# Application lifecycle events using modern lifespan


async def perform_direct_ecourts_scraping(scraper, state_code, district_code, 
                                        court_complex_code, court_code, from_date):
    """
    Perform direct scraping of eCourts portal.
    
    Args:
        scraper: RealECourtsScraper instance
        state_code: State code
        district_code: District code  
        court_complex_code: Court complex code
        court_code: Court code
        from_date: From date
        to_date: To date
        
    Returns:
        Dictionary with scraping result
    """
    try:
        logger.info("Starting direct eCourts scraping...")
        
        # Check if scraper is properly initialized
        if not scraper:
            raise Exception("Scraper not initialized")
        
        # Navigate to eCourts portal and extract cause list
        result = scraper.scrape_cause_list_direct(
            state_code=state_code,
            district_code=district_code,
            court_complex_code=court_complex_code,
            court_code=court_code,
            date=from_date
        )
        
        if result and result.get('success'):
            # Generate filename
            filename = f"cause_list_{from_date}_{court_complex_code}.pdf"
            
            # Save the scraped data as PDF
            download_url = f"/downloads/{filename}"
            file_path = os.path.join(DOWNLOADS_DIR, filename)
            
            # Ensure downloads directory exists
            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            
            # Create PDF from scraped data
            pdf_result = create_pdf_from_scraped_data(result['data'], file_path)
            
            if pdf_result['success']:
                logger.info(f"Successfully created PDF: {filename}")
                return {
                    'success': True,
                    'filename': filename,
                    'downloadUrl': download_url,
                    'size': pdf_result.get('size', '245 KB'),
                    'sizeBytes': pdf_result.get('sizeBytes', 250880),
                    'data': result['data']
                }
        
        logger.warning("Scraping returned no data")
        return {'success': False, 'error': 'No data found'}
        
    except Exception as e:
        logger.error(f"Direct scraping error: {str(e)}")
        return {'success': False, 'error': str(e)}

def create_pdf_from_scraped_data(scraped_data, file_path):
    """
    Create PDF from scraped cause list data.
    
    Args:
        scraped_data: Data scraped from eCourts portal
        file_path: Path to save PDF file
        
    Returns:
        Dictionary with creation result
    """
    try:
        # Use the PDF generator if available
        from utils.pdf_generator import create_cause_list_pdf_from_data
        
        result = create_cause_list_pdf_from_data(scraped_data, file_path)
        return result
        
    except ImportError:
        # Fallback to basic text file
        logger.warning("PDF generator not available, creating text file")
        
        content = format_scraped_data_as_text(scraped_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        file_size = len(content.encode('utf-8'))
        
        return {
            'success': True,
            'size': f"{file_size // 1024} KB",
            'sizeBytes': file_size
        }

def format_scraped_data_as_text(data):
    """Format scraped data as readable text."""
    content = f"""CAUSE LIST - {data.get('court_name', 'Court')}
Date: {data.get('date', 'N/A')}
Judge: {data.get('judge', 'N/A')}

CASES FOR HEARING
================

"""
    
    cases = data.get('cases', [])
    if cases:
        for i, case in enumerate(cases, 1):
            content += f"{i}. {case.get('case_number', 'N/A')} - {case.get('parties', 'N/A')} - {case.get('advocate', 'N/A')} - {case.get('stage', 'N/A')}\n"
    else:
        content += "No cases listed for this date.\n"
    
    content += f"\n\nGenerated by eCourts Scraper: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    return content

def create_fallback_pdf(state_code, district_code, court_complex_code, date):
    """
    Create a fallback PDF when scraping fails.
    
    Args:
        state_code: State code
        district_code: District code
        court_complex_code: Court complex code
        date: Date string
        
    Returns:
        Dictionary with file information
    """
    try:
        filename = f"cause_list_{date}_{court_complex_code}_fallback.pdf"
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        
        # Ensure downloads directory exists
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        
        # Create fallback content
        fallback_data = {
            'court_name': f"{court_complex_code} Court Complex",
            'date': date,
            'judge': "Hon'ble Court",
            'cases': [
                {
                    'case_number': 'DEMO/001/2024',
                    'parties': 'Demo Case vs. Example Party',
                    'advocate': 'Demo Advocate',
                    'stage': 'For Arguments'
                }
            ]
        }
        
        content = format_scraped_data_as_text(fallback_data)
        content = f"[DEMO MODE - eCourts Portal Unavailable]\n\n{content}"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        file_size = len(content.encode('utf-8'))
        
        return {
            'filename': filename,
            'downloadUrl': f"/downloads/{filename}",
            'size': f"{file_size // 1024} KB",
            'sizeBytes': file_size
        }
        
    except Exception as e:
        logger.error(f"Error creating fallback PDF: {str(e)}")
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port, reload=settings.debug)