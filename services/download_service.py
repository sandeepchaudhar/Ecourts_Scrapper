"""
Download Service for eCourts Cause List Scraper.

This module provides the DownloadService class for managing PDF downloads,
file operations, and ZIP archive creation with comprehensive error handling.
"""

import os
import zipfile
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

from models.court_models import (
    DownloadRequest, DownloadResult, BulkDownloadRequest, 
    BulkDownloadResult, ErrorResponse
)
from scraper.ecourts_scraper import ECourtsScraper
from config import settings, DOWNLOADS_DIR

# Configure logging
logger = logging.getLogger(__name__)


class DownloadService:
    """
    Service class for managing cause list downloads and file operations.
    
    Handles individual and bulk downloads, file management, ZIP archive creation,
    and provides comprehensive error handling and progress tracking.
    """
    
    def __init__(self, base_download_dir: str = None):
        """
        Initialize the download service.
        
        Args:
            base_download_dir: Base directory for downloads (defaults to config setting)
        """
        self.base_download_dir = Path(base_download_dir) if base_download_dir else DOWNLOADS_DIR
        self.scraper = ECourtsScraper()
        
        # Ensure base download directory exists
        self.base_download_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DownloadService initialized with base directory: {self.base_download_dir}")
    
    def create_download_directory(self, date: str) -> Path:
        """
        Create and return a date-specific download directory.
        
        Args:
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Path object for the created directory
        """
        try:
            # Create date-based subdirectory
            date_dir = self.base_download_dir / date
            date_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Created download directory: {date_dir}")
            return date_dir
            
        except Exception as e:
            logger.error(f"Error creating download directory for date {date}: {str(e)}")
            # Fallback to base directory
            return self.base_download_dir
    
    def generate_filename(self, court_name: str, date: str, court_code: str = None) -> str:
        """
        Generate a standardized filename for cause list PDFs.
        
        Args:
            court_name: Name of the court
            date: Date in YYYY-MM-DD format
            court_code: Optional court code for uniqueness
            
        Returns:
            Generated filename string
        """
        try:
            # Clean court name for filename
            clean_court_name = "".join(c for c in court_name if c.isalnum() or c in (' ', '-', '_')).strip()
            clean_court_name = clean_court_name.replace(' ', '_').replace('-', '_')
            
            # Limit length to avoid filesystem issues
            if len(clean_court_name) > 50:
                clean_court_name = clean_court_name[:50]
            
            # Format date for filename
            date_str = date.replace('-', '_')
            
            # Generate filename with optional court code
            if court_code:
                filename = f"{clean_court_name}_{court_code}_{date_str}.pdf"
            else:
                filename = f"{clean_court_name}_{date_str}.pdf"
            
            logger.debug(f"Generated filename: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error generating filename: {str(e)}")
            # Fallback filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"causelist_{timestamp}.pdf"
    
    def save_pdf(self, content: bytes, filepath: Path) -> bool:
        """
        Save PDF content to the specified file path.
        
        Args:
            content: PDF content as bytes
            filepath: Path where to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content to file
            with open(filepath, 'wb') as f:
                f.write(content)
            
            # Verify file was created and has content
            if filepath.exists() and filepath.stat().st_size > 0:
                logger.info(f"Successfully saved PDF: {filepath} ({filepath.stat().st_size} bytes)")
                return True
            else:
                logger.error(f"Failed to save PDF or file is empty: {filepath}")
                return False
                
        except Exception as e:
            logger.error(f"Error saving PDF to {filepath}: {str(e)}")
            return False
    
    def get_file_info(self, filepath: Path) -> Dict[str, Any]:
        """
        Get information about a downloaded file.
        
        Args:
            filepath: Path to the file
            
        Returns:
            Dictionary with file information
        """
        try:
            if not filepath.exists():
                return {
                    'exists': False,
                    'size': 0,
                    'created': None,
                    'modified': None,
                    'error': 'File does not exist'
                }
            
            stat = filepath.stat()
            
            return {
                'exists': True,
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'name': filepath.name,
                'path': str(filepath),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error getting file info for {filepath}: {str(e)}")
            return {
                'exists': False,
                'size': 0,
                'created': None,
                'modified': None,
                'error': str(e)
            }
    
    def create_zip_archive(self, file_paths: List[Path], zip_filename: str, 
                          zip_directory: Path = None) -> Optional[Path]:
        """
        Create a ZIP archive containing the specified files.
        
        Args:
            file_paths: List of file paths to include in the archive
            zip_filename: Name for the ZIP file
            zip_directory: Directory to create the ZIP file (defaults to base download dir)
            
        Returns:
            Path to the created ZIP file, or None if failed
        """
        try:
            if not file_paths:
                logger.warning("No files provided for ZIP archive creation")
                return None
            
            # Use provided directory or default to base download directory
            if zip_directory is None:
                zip_directory = self.base_download_dir
            
            zip_path = zip_directory / zip_filename
            
            # Create ZIP file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in file_paths:
                    if file_path.exists():
                        # Add file to ZIP with just the filename (no directory structure)
                        zipf.write(file_path, file_path.name)
                        logger.debug(f"Added {file_path.name} to ZIP archive")
                    else:
                        logger.warning(f"File not found, skipping: {file_path}")
            
            # Verify ZIP file was created
            if zip_path.exists() and zip_path.stat().st_size > 0:
                logger.info(f"Successfully created ZIP archive: {zip_path} ({zip_path.stat().st_size} bytes)")
                return zip_path
            else:
                logger.error(f"Failed to create ZIP archive: {zip_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating ZIP archive: {str(e)}")
            return None
    
    def download_single_cause_list(self, request: DownloadRequest) -> DownloadResult:
        """
        Download a single cause list PDF.
        
        Args:
            request: Download request with court and date information
            
        Returns:
            DownloadResult with success status and file information
        """
        try:
            logger.info(f"Starting single download for court {request.court_code} on {request.date}")
            
            # Create download directory for the date
            download_dir = self.create_download_directory(request.date)
            
            # Get court name for filename generation (this would typically come from a previous API call)
            # For now, we'll use the court code
            court_name = f"Court_{request.court_code}"
            
            # Generate filename
            filename = self.generate_filename(court_name, request.date, request.court_code)
            filepath = download_dir / filename
            
            # Download using the scraper
            download_result = self.scraper.download_cause_list_by_court_and_date(
                court_code=request.court_code,
                date=request.date,
                court_name=court_name
            )
            
            if download_result['success']:
                # Move the downloaded file to our organized structure if needed
                source_path = Path(download_result['filepath'])
                if source_path != filepath:
                    shutil.move(str(source_path), str(filepath))
                
                # Generate download URL (relative to static directory)
                relative_path = filepath.relative_to(self.base_download_dir.parent)
                download_url = f"/{relative_path.as_posix()}"
                
                return DownloadResult(
                    success=True,
                    filename=filename,
                    file_size=download_result['file_size'],
                    download_url=download_url,
                    error_message=None
                )
            else:
                # Ensure we have valid non-empty values for validation
                safe_filename = filename if filename and filename.strip() else "failed_download.pdf"
                safe_download_url = "/static/downloads/not_available.pdf"
                error_msg = download_result.get('error_message', 'Unknown download error')
                
                return DownloadResult(
                    success=False,
                    filename=safe_filename,
                    file_size=0,
                    download_url=safe_download_url,
                    error_message=error_msg
                )
                
        except Exception as e:
            logger.error(f"Error in single download: {str(e)}")
            # Generate a fallback filename - ensure it's not empty
            fallback_filename = f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            safe_download_url = "/static/downloads/error.pdf"
            
            return DownloadResult(
                success=False,
                filename=fallback_filename,
                file_size=0,
                download_url=safe_download_url,
                error_message=f"Download service error: {str(e)}"
            )
    
    def identify_courts_in_complex(self, complex_code: str) -> List[Dict[str, str]]:
        """
        Identify all courts within a given court complex.
        
        Args:
            complex_code: Court complex code
            
        Returns:
            List of court dictionaries with code and name
        """
        try:
            logger.info(f"Identifying courts in complex: {complex_code}")
            
            courts = self.scraper.get_courts(complex_code)
            
            logger.info(f"Found {len(courts)} courts in complex {complex_code}")
            return courts
            
        except Exception as e:
            logger.error(f"Error identifying courts in complex {complex_code}: {str(e)}")
            return []
    
    def download_bulk_cause_lists(self, request: BulkDownloadRequest, 
                                 progress_callback: Optional[callable] = None) -> BulkDownloadResult:
        """
        Download cause lists for all courts in a complex (bulk download).
        
        Args:
            request: Bulk download request
            progress_callback: Optional callback function for progress updates
            
        Returns:
            BulkDownloadResult with overall status and individual results
        """
        try:
            logger.info(f"Starting bulk download for complex {request.complex_code} on {request.date}")
            
            # Identify all courts in the complex
            courts = self.identify_courts_in_complex(request.complex_code)
            
            if not courts:
                return BulkDownloadResult(
                    success=False,
                    total_files=0,
                    successful_downloads=0,
                    failed_downloads=0,
                    download_results=[],
                    zip_filename=None,
                    zip_download_url=None
                )
            
            total_courts = len(courts)
            download_results = []
            successful_files = []
            
            # Create download directory
            download_dir = self.create_download_directory(request.date)
            
            # Download each court's cause list
            with ThreadPoolExecutor(max_workers=3) as executor:  # Limit concurrent downloads
                # Submit all download tasks
                future_to_court = {}
                for court in courts:
                    download_request = DownloadRequest(
                        state_code=request.state_code,
                        district_code=request.district_code,
                        complex_code=request.complex_code,
                        court_code=court['code'],
                        date=request.date
                    )
                    
                    future = executor.submit(self.download_single_cause_list, download_request)
                    future_to_court[future] = court
                
                # Process completed downloads
                completed = 0
                for future in as_completed(future_to_court):
                    court = future_to_court[future]
                    completed += 1
                    
                    try:
                        result = future.result()
                        download_results.append(result)
                        
                        if result.success:
                            # Add to successful files list for ZIP creation
                            filepath = download_dir / result.filename
                            if filepath.exists():
                                successful_files.append(filepath)
                        
                        # Call progress callback if provided
                        if progress_callback:
                            progress_callback(completed, total_courts, court['name'], result.success)
                            
                    except Exception as e:
                        logger.error(f"Error downloading for court {court['name']}: {str(e)}")
                        # Generate safe fallback values to avoid validation errors
                        error_filename = f"error_{court.get('code', 'unknown')}_{request.date.replace('-', '_')}.pdf"
                        error_result = DownloadResult(
                            success=False,
                            filename=error_filename,
                            file_size=0,
                            download_url="/static/downloads/error.pdf",
                            error_message=str(e)
                        )
                        download_results.append(error_result)
            
            # Calculate statistics
            successful_downloads = sum(1 for r in download_results if r.success)
            failed_downloads = total_courts - successful_downloads
            
            # Create ZIP archive if there are successful downloads
            zip_filename = None
            zip_download_url = None
            
            if successful_files:
                zip_filename = f"bulk_download_{request.complex_code}_{request.date.replace('-', '_')}.zip"
                zip_path = self.create_zip_archive(successful_files, zip_filename, download_dir)
                
                if zip_path:
                    # Generate ZIP download URL
                    relative_path = zip_path.relative_to(self.base_download_dir.parent)
                    zip_download_url = f"/{relative_path.as_posix()}"
            
            # Determine overall success
            overall_success = successful_downloads > 0
            
            logger.info(f"Bulk download completed: {successful_downloads}/{total_courts} successful")
            
            return BulkDownloadResult(
                success=overall_success,
                total_files=total_courts,
                successful_downloads=successful_downloads,
                failed_downloads=failed_downloads,
                download_results=download_results,
                zip_filename=zip_filename,
                zip_download_url=zip_download_url
            )
            
        except Exception as e:
            logger.error(f"Error in bulk download: {str(e)}")
            return BulkDownloadResult(
                success=False,
                total_files=0,
                successful_downloads=0,
                failed_downloads=0,
                download_results=[],
                zip_filename=None,
                zip_download_url=None
            )
    
    def cleanup_old_files(self, days_old: int = 7) -> Dict[str, Any]:
        """
        Clean up downloaded files older than specified days.
        
        Args:
            days_old: Number of days after which files should be cleaned up
            
        Returns:
            Dictionary with cleanup statistics
        """
        try:
            from datetime import timedelta
            
            cutoff_time = datetime.now() - timedelta(days=days_old)
            deleted_files = 0
            deleted_size = 0
            errors = []
            
            # Walk through all files in download directory
            for root, dirs, files in os.walk(self.base_download_dir):
                for file in files:
                    filepath = Path(root) / file
                    try:
                        # Check file modification time
                        if filepath.stat().st_mtime < cutoff_time.timestamp():
                            file_size = filepath.stat().st_size
                            filepath.unlink()
                            deleted_files += 1
                            deleted_size += file_size
                            logger.debug(f"Deleted old file: {filepath}")
                    except Exception as e:
                        errors.append(f"Error deleting {filepath}: {str(e)}")
            
            # Clean up empty directories
            for root, dirs, files in os.walk(self.base_download_dir, topdown=False):
                for dir_name in dirs:
                    dir_path = Path(root) / dir_name
                    try:
                        if not any(dir_path.iterdir()):  # Directory is empty
                            dir_path.rmdir()
                            logger.debug(f"Deleted empty directory: {dir_path}")
                    except Exception as e:
                        errors.append(f"Error deleting directory {dir_path}: {str(e)}")
            
            logger.info(f"Cleanup completed: {deleted_files} files deleted, {deleted_size} bytes freed")
            
            return {
                'success': True,
                'deleted_files': deleted_files,
                'deleted_size': deleted_size,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            return {
                'success': False,
                'deleted_files': 0,
                'deleted_size': 0,
                'errors': [str(e)]
            }
    
    def get_download_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about downloaded files.
        
        Returns:
            Dictionary with download statistics
        """
        try:
            total_files = 0
            total_size = 0
            file_types = {}
            date_directories = []
            
            # Walk through download directory
            for root, dirs, files in os.walk(self.base_download_dir):
                # Track date directories
                root_path = Path(root)
                if root_path != self.base_download_dir:
                    relative_path = root_path.relative_to(self.base_download_dir)
                    if len(relative_path.parts) == 1:  # Direct subdirectory (likely date)
                        date_directories.append(str(relative_path))
                
                for file in files:
                    filepath = Path(root) / file
                    try:
                        file_stat = filepath.stat()
                        total_files += 1
                        total_size += file_stat.st_size
                        
                        # Track file types
                        file_ext = filepath.suffix.lower()
                        file_types[file_ext] = file_types.get(file_ext, 0) + 1
                        
                    except Exception as e:
                        logger.warning(f"Error getting stats for {filepath}: {str(e)}")
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'file_types': file_types,
                'date_directories': sorted(date_directories),
                'base_directory': str(self.base_download_dir)
            }
            
        except Exception as e:
            logger.error(f"Error getting download statistics: {str(e)}")
            return {
                'total_files': 0,
                'total_size': 0,
                'file_types': {},
                'date_directories': [],
                'base_directory': str(self.base_download_dir),
                'error': str(e)
            }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        if hasattr(self.scraper, 'close_session'):
            self.scraper.close_session()


class ProgressTracker:
    """
    Progress tracking utility for bulk downloads.
    
    Provides real-time progress updates and status tracking for multiple
    concurrent download operations.
    """
    
    def __init__(self, total_items: int):
        """
        Initialize progress tracker.
        
        Args:
            total_items: Total number of items to track
        """
        self.total_items = total_items
        self.completed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.current_item = None
        self.start_time = datetime.now()
        self.callbacks = []
        
        logger.info(f"ProgressTracker initialized for {total_items} items")
    
    def add_callback(self, callback: callable):
        """
        Add a progress callback function.
        
        Args:
            callback: Function to call with progress updates
        """
        self.callbacks.append(callback)
    
    def update_progress(self, item_name: str, success: bool, error_message: str = None):
        """
        Update progress for a completed item.
        
        Args:
            item_name: Name of the completed item
            success: Whether the item was processed successfully
            error_message: Optional error message for failed items
        """
        self.completed_items += 1
        self.current_item = item_name
        
        if success:
            self.successful_items += 1
        else:
            self.failed_items += 1
        
        # Calculate progress percentage
        progress_percent = (self.completed_items / self.total_items) * 100
        
        # Calculate estimated time remaining
        elapsed_time = datetime.now() - self.start_time
        if self.completed_items > 0:
            avg_time_per_item = elapsed_time.total_seconds() / self.completed_items
            remaining_items = self.total_items - self.completed_items
            estimated_remaining = remaining_items * avg_time_per_item
        else:
            estimated_remaining = 0
        
        # Create progress info
        progress_info = {
            'total_items': self.total_items,
            'completed_items': self.completed_items,
            'successful_items': self.successful_items,
            'failed_items': self.failed_items,
            'current_item': item_name,
            'progress_percent': round(progress_percent, 2),
            'elapsed_seconds': elapsed_time.total_seconds(),
            'estimated_remaining_seconds': estimated_remaining,
            'success': success,
            'error_message': error_message
        }
        
        # Call all registered callbacks
        for callback in self.callbacks:
            try:
                callback(progress_info)
            except Exception as e:
                logger.warning(f"Error in progress callback: {str(e)}")
        
        logger.info(f"Progress: {self.completed_items}/{self.total_items} ({progress_percent:.1f}%) - {item_name}")
    
    def is_complete(self) -> bool:
        """Check if all items have been processed."""
        return self.completed_items >= self.total_items
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the progress tracking.
        
        Returns:
            Dictionary with progress summary
        """
        elapsed_time = datetime.now() - self.start_time
        
        return {
            'total_items': self.total_items,
            'completed_items': self.completed_items,
            'successful_items': self.successful_items,
            'failed_items': self.failed_items,
            'success_rate': (self.successful_items / self.total_items * 100) if self.total_items > 0 else 0,
            'elapsed_seconds': elapsed_time.total_seconds(),
            'is_complete': self.is_complete()
        }


class BulkDownloadManager:
    """
    Enhanced bulk download manager with advanced progress tracking and error handling.
    
    Provides sophisticated bulk download capabilities with real-time progress updates,
    retry mechanisms, and detailed error reporting.
    """
    
    def __init__(self, download_service: DownloadService):
        """
        Initialize bulk download manager.
        
        Args:
            download_service: DownloadService instance to use for downloads
        """
        self.download_service = download_service
        self.active_downloads = {}
        
        logger.info("BulkDownloadManager initialized")
    
    def start_bulk_download(self, request: BulkDownloadRequest, 
                           progress_callback: Optional[callable] = None,
                           max_concurrent: int = 3,
                           retry_failed: bool = True) -> str:
        """
        Start a bulk download operation with enhanced tracking.
        
        Args:
            request: Bulk download request
            progress_callback: Optional callback for progress updates
            max_concurrent: Maximum number of concurrent downloads
            retry_failed: Whether to retry failed downloads
            
        Returns:
            Download session ID for tracking
        """
        import uuid
        
        session_id = str(uuid.uuid4())
        
        # Create progress tracker
        courts = self.download_service.identify_courts_in_complex(request.complex_code)
        progress_tracker = ProgressTracker(len(courts))
        
        if progress_callback:
            progress_tracker.add_callback(progress_callback)
        
        # Store session info
        self.active_downloads[session_id] = {
            'request': request,
            'progress_tracker': progress_tracker,
            'courts': courts,
            'status': 'starting',
            'start_time': datetime.now(),
            'results': None
        }
        
        # Start download in background thread
        import threading
        
        def run_bulk_download():
            try:
                self.active_downloads[session_id]['status'] = 'running'
                
                # Use the existing bulk download method with progress tracking
                def progress_update(completed, total, court_name, success):
                    progress_tracker.update_progress(court_name, success)
                
                results = self.download_service.download_bulk_cause_lists(
                    request, progress_callback=progress_update
                )
                
                self.active_downloads[session_id]['results'] = results
                self.active_downloads[session_id]['status'] = 'completed'
                
            except Exception as e:
                logger.error(f"Error in bulk download session {session_id}: {str(e)}")
                self.active_downloads[session_id]['status'] = 'error'
                self.active_downloads[session_id]['error'] = str(e)
        
        thread = threading.Thread(target=run_bulk_download)
        thread.daemon = True
        thread.start()
        
        logger.info(f"Started bulk download session: {session_id}")
        return session_id
    
    def get_download_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get the status of a bulk download session.
        
        Args:
            session_id: Download session ID
            
        Returns:
            Dictionary with session status and progress
        """
        if session_id not in self.active_downloads:
            return {'error': 'Session not found'}
        
        session = self.active_downloads[session_id]
        
        status_info = {
            'session_id': session_id,
            'status': session['status'],
            'start_time': session['start_time'],
            'progress': session['progress_tracker'].get_summary()
        }
        
        if session['status'] == 'completed' and session.get('results'):
            status_info['results'] = session['results']
        
        if session['status'] == 'error' and session.get('error'):
            status_info['error'] = session['error']
        
        return status_info
    
    def cancel_download(self, session_id: str) -> bool:
        """
        Cancel an active bulk download session.
        
        Args:
            session_id: Download session ID
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        if session_id not in self.active_downloads:
            return False
        
        try:
            self.active_downloads[session_id]['status'] = 'cancelled'
            logger.info(f"Cancelled bulk download session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling session {session_id}: {str(e)}")
            return False
    
    def cleanup_completed_sessions(self, max_age_hours: int = 24):
        """
        Clean up completed download sessions older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours for keeping completed sessions
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        sessions_to_remove = []
        
        for session_id, session in self.active_downloads.items():
            if (session['status'] in ['completed', 'error', 'cancelled'] and 
                session['start_time'] < cutoff_time):
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self.active_downloads[session_id]
            logger.debug(f"Cleaned up old session: {session_id}")
        
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old download sessions")
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get information about all active download sessions.
        
        Returns:
            List of active session information
        """
        active_sessions = []
        
        for session_id, session in self.active_downloads.items():
            session_info = {
                'session_id': session_id,
                'status': session['status'],
                'start_time': session['start_time'],
                'total_courts': len(session['courts']),
                'progress': session['progress_tracker'].get_summary()
            }
            active_sessions.append(session_info)
        
        return active_sessions