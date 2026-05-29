import logging
import json
import os
import sys
import functools
import traceback
from datetime import datetime, timezone

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kws)

logging.Logger.trace = trace

class StrictFileHandler(logging.FileHandler):
    """
    A FileHandler that strictly enforces 'No Logging, No Action'.
    If a disk write fails, the application panics and halts.
    It forces an fsync for TRACE and ERROR levels to ensure data is written to disk.
    """
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
            if record.levelno in (TRACE_LEVEL, logging.ERROR, logging.CRITICAL):
                os.fsync(stream.fileno())
        except Exception:
            self.handleError(record)

    def handleError(self, record):
        # Panic mode
        sys.stderr.write(f"CRITICAL LOGGING FAILURE. 'No Logging, No Action' policy triggered.\n")
        sys.stderr.write(f"Failed to write record: {record}\n")
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        if hasattr(record, "event_data"):
            log_record.update(record.event_data)
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_exhaustive_logging(log_file_path: str):
    logger = logging.getLogger()
    logger.setLevel(TRACE_LEVEL)
    
    # Remove existing handlers to prevent duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    log_dir = os.path.dirname(log_file_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = StrictFileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)  # Keep stdout clean for normal viewing
    stream_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s — %(message)s'))
    
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger

def exhaustive_log(func):
    """
    Decorator to log every speck of dust (entry, arguments, exit, return values, exceptions).
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        
        # Sanitize common secrets from kwargs
        safe_kwargs = kwargs.copy()
        for key in ["api_key", "secret", "password", "token"]:
            if key in safe_kwargs:
                safe_kwargs[key] = "***REDACTED***"
                
        # Handle args that might be secrets (best effort)
        safe_args = tuple("***REDACTED***" if isinstance(a, str) and (a.startswith("sk-") or a.startswith("nvapi-")) else a for a in args)

        logger.trace(
            f"Entering {func.__name__}", 
            extra={"event_data": {"event": "function_enter", "function": func.__name__, "args": str(safe_args), "kwargs": str(safe_kwargs)}}
        )
        
        start_time = datetime.now(timezone.utc)
        try:
            result = func(*args, **kwargs)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.trace(
                f"Exiting {func.__name__}", 
                extra={"event_data": {"event": "function_exit", "function": func.__name__, "duration_ms": duration_ms, "return_type": type(result).__name__, "return_value": str(result)[:500]}} # Truncate massive returns
            )
            return result
        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.error(
                f"Exception in {func.__name__}: {str(e)}", 
                exc_info=True,
                extra={"event_data": {"event": "function_exception", "function": func.__name__, "duration_ms": duration_ms}}
            )
            raise
    return wrapper
