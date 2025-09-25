"""
Enhanced shutdown logging system that writes directly to file without using Python's logging module.
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class ShutdownFileLogger:
    """Custom logger that writes shutdown messages directly to a file with timestamps."""
    
    def __init__(self, log_file: str = "last_run.txt", log_dir: Optional[Path] = None):
        """
        Initialize the shutdown file logger.
        
        Args:
            log_file: Name of the log file
            log_dir: Directory to store log file (defaults to current directory)
        """
        self.log_dir = log_dir or Path.cwd()
        self.log_file = self.log_dir / log_file
        
        # Ensure directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Open file in write mode to overwrite previous run
        self.file_handle = open(self.log_file, 'w', encoding='utf-8', buffering=1)
        
        # Write header to file
        self._write_header()
    
    def _write_header(self):
        """Write a header to the log file."""
        self._write_line("INFO", "=" * 80)
        self._write_line("INFO", f"SHUTDOWN LOG - Started at {datetime.now().isoformat()}")
        self._write_line("INFO", "=" * 80)
    
    def _write_line(self, level: str, message: str):
        """Write a formatted line to the log file."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Include milliseconds
        formatted_line = f"{timestamp} | {level:<8} | {message}\n"
        
        try:
            self.file_handle.write(formatted_line)
            self.file_handle.flush()  # Ensure immediate write
        except Exception:
            # If writing fails, silently continue (don't let logging break the app)
            pass
    
    def debug(self, msg: str, *args):
        """Write debug message."""
        if args:
            try:
                msg = msg % args
            except:
                pass
        self._write_line("DEBUG", msg)
    
    def info(self, msg: str, *args):
        """Write info message."""
        if args:
            try:
                msg = msg % args
            except:
                pass
        self._write_line("INFO", msg)
    
    def warning(self, msg: str, *args):
        """Write warning message."""
        if args:
            try:
                msg = msg % args
            except:
                pass
        self._write_line("WARNING", msg)
    
    def error(self, msg: str, *args):
        """Write error message."""
        if args:
            try:
                msg = msg % args
            except:
                pass
        self._write_line("ERROR", msg)
    
    def critical(self, msg: str, *args):
        """Write critical message."""
        if args:
            try:
                msg = msg % args
            except:
                pass
        self._write_line("CRITICAL", msg)
    
    def write_footer(self):
        """Write a footer when shutdown completes."""
        self._write_line("INFO", "=" * 80)
        self._write_line("INFO", f"SHUTDOWN COMPLETED - Ended at {datetime.now().isoformat()}")
        self._write_line("INFO", "=" * 80)
    
    def flush(self):
        """Flush the file handle to ensure data is written."""
        try:
            if self.file_handle and not self.file_handle.closed:
                self.file_handle.flush()
        except Exception:
            pass
    
    def close(self):
        """Close the file handle."""
        try:
            if self.file_handle and not self.file_handle.closed:
                self.file_handle.close()
        except Exception:
            pass


class ShutdownLogger:
    """
    Singleton logger wrapper for shutdown operations.
    This ensures we use the same logger instance throughout the shutdown process.
    """
    _instance = None
    _file_logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, log_file: str = "last_run.txt", log_dir: Optional[Path] = None):
        """Initialize the logger if not already initialized."""
        if self._file_logger is None:
            self._file_logger = ShutdownFileLogger(log_file, log_dir)
    
    def complete(self):
        """Mark shutdown as complete and close the log file."""
        if self._file_logger:
            self._file_logger.write_footer()
            self._file_logger.flush()
            self._file_logger.close()
    
    def flush(self):
        """Flush the log file."""
        if self._file_logger:
            self._file_logger.flush()
    
    def debug(self, msg, *args, **kwargs):
        """Log debug message."""
        if self._file_logger:
            self._file_logger.debug(msg, *args)
    
    def info(self, msg, *args, **kwargs):
        """Log info message."""
        if self._file_logger:
            self._file_logger.info(msg, *args)
    
    def warning(self, msg, *args, **kwargs):
        """Log warning message."""
        if self._file_logger:
            self._file_logger.warning(msg, *args)
    
    def error(self, msg, *args, **kwargs):
        """Log error message."""
        if self._file_logger:
            self._file_logger.error(msg, *args)
    
    def critical(self, msg, *args, **kwargs):
        """Log critical message."""
        if self._file_logger:
            self._file_logger.critical(msg, *args)


# Create a global instance
shutdown_logger = ShutdownLogger()