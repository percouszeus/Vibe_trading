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
            stream = self.stream
            if stream is None:
                return
            msg = self.format(record)
            stream.write(msg + self.terminator)
            self.flush()
            if record.levelno in (logging.ERROR, logging.CRITICAL):
                try:
                    if hasattr(stream, "fileno") and not stream.closed:
                        os.fsync(stream.fileno())
                except (OSError, ValueError):
                    pass
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

_network_patched = False

def patch_network_libraries():
    global _network_patched
    if _network_patched:
        return
    _network_patched = True

    # 1. requests patch
    try:
        import requests
        if not hasattr(requests.Session.send, "_is_patched"):
            requests_original_send = requests.Session.send

            @functools.wraps(requests_original_send)
            def new_send(self, request, **kwargs):
                logger = logging.getLogger("network.requests")
                
                # Sanitize headers
                headers = dict(request.headers)
                for k in list(headers.keys()):
                    if any(x in k.lower() for x in ["auth", "key", "token", "cookie", "secret"]):
                        headers[k] = "***REDACTED***"
                
                url = request.url
                method = request.method
                body = request.body
                if isinstance(body, bytes):
                    try:
                        body = body.decode('utf-8', errors='ignore')
                    except Exception:
                        body = "<binary data>"
                
                logger.trace(
                    f"HTTP Request: {method} {url}",
                    extra={"event_data": {
                        "event": "http_request",
                        "library": "requests",
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "body": str(body)[:1000] if body else None
                    }}
                )
                
                start_time = datetime.now(timezone.utc)
                try:
                    response = requests_original_send(self, request, **kwargs)
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    resp_headers = dict(response.headers)
                    for k in list(resp_headers.keys()):
                        if any(x in k.lower() for x in ["cookie", "set-cookie", "token", "auth", "key"]):
                            resp_headers[k] = "***REDACTED***"
                    
                    resp_body = ""
                    try:
                        resp_body = response.text
                    except Exception:
                        resp_body = "<undecodable>"
                    
                    logger.trace(
                        f"HTTP Response: {method} {url} | Status: {response.status_code}",
                        extra={"event_data": {
                            "event": "http_response",
                            "library": "requests",
                            "method": method,
                            "url": url,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms,
                            "headers": resp_headers,
                            "body": str(resp_body)[:2000] if resp_body else None
                        }}
                    )
                    return response
                except Exception as e:
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    logger.error(
                        f"HTTP Request Failed: {method} {url} | Error: {str(e)}",
                        extra={"event_data": {
                            "event": "http_error",
                            "library": "requests",
                            "method": method,
                            "url": url,
                            "duration_ms": duration_ms,
                            "error": str(e)
                        }}
                    )
                    raise
            new_send._is_patched = True
            requests.Session.send = new_send
    except ImportError:
        pass

    # 2. httpx patch
    try:
        import httpx
        if not hasattr(httpx.Client.send, "_is_patched"):
            httpx_original_send = httpx.Client.send
            
            @functools.wraps(httpx_original_send)
            def new_send(self, request, **kwargs):
                logger = logging.getLogger("network.httpx")
                
                headers = dict(request.headers)
                for k in list(headers.keys()):
                    if any(x in k.lower() for x in ["auth", "key", "token", "cookie", "secret"]):
                        headers[k] = "***REDACTED***"
                
                url = str(request.url)
                method = request.method
                
                body = ""
                try:
                    body = request.content.decode('utf-8', errors='ignore') if request.content else ""
                except Exception:
                    body = "<binary or streaming data>"
                
                logger.trace(
                    f"HTTP Request: {method} {url}",
                    extra={"event_data": {
                        "event": "http_request",
                        "library": "httpx_sync",
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "body": str(body)[:1000] if body else None
                    }}
                )
                
                start_time = datetime.now(timezone.utc)
                try:
                    response = httpx_original_send(self, request, **kwargs)
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    resp_headers = dict(response.headers)
                    for k in list(resp_headers.keys()):
                        if any(x in k.lower() for x in ["cookie", "set-cookie", "token", "auth", "key"]):
                            resp_headers[k] = "***REDACTED***"
                    
                    resp_body = ""
                    try:
                        resp_body = response.text
                    except Exception:
                        resp_body = "<undecodable or streaming>"
                    
                    logger.trace(
                        f"HTTP Response: {method} {url} | Status: {response.status_code}",
                        extra={"event_data": {
                            "event": "http_response",
                            "library": "httpx_sync",
                            "method": method,
                            "url": url,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms,
                            "headers": resp_headers,
                            "body": str(resp_body)[:2000] if resp_body else None
                        }}
                    )
                    return response
                except Exception as e:
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    logger.error(
                        f"HTTP Request Failed: {method} {url} | Error: {str(e)}",
                        extra={"event_data": {
                            "event": "http_error",
                            "library": "httpx_sync",
                            "method": method,
                            "url": url,
                            "duration_ms": duration_ms,
                            "error": str(e)
                        }}
                    )
                    raise
            new_send._is_patched = True
            httpx.Client.send = new_send

            # Patch AsyncClient
            httpx_async_original_send = httpx.AsyncClient.send
            
            @functools.wraps(httpx_async_original_send)
            async def new_async_send(self, request, **kwargs):
                logger = logging.getLogger("network.httpx_async")
                
                headers = dict(request.headers)
                for k in list(headers.keys()):
                    if any(x in k.lower() for x in ["auth", "key", "token", "cookie", "secret"]):
                        headers[k] = "***REDACTED***"
                
                url = str(request.url)
                method = request.method
                
                body = ""
                try:
                    body = request.content.decode('utf-8', errors='ignore') if request.content else ""
                except Exception:
                    body = "<binary or streaming data>"
                
                logger.trace(
                    f"HTTP Request: {method} {url}",
                    extra={"event_data": {
                        "event": "http_request",
                        "library": "httpx_async",
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "body": str(body)[:1000] if body else None
                    }}
                )
                
                start_time = datetime.now(timezone.utc)
                try:
                    response = await httpx_async_original_send(self, request, **kwargs)
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    
                    resp_headers = dict(response.headers)
                    for k in list(resp_headers.keys()):
                        if any(x in k.lower() for x in ["cookie", "set-cookie", "token", "auth", "key"]):
                            resp_headers[k] = "***REDACTED***"
                    
                    resp_body = ""
                    try:
                        resp_body = response.text
                    except Exception:
                        resp_body = "<undecodable or streaming>"
                    
                    logger.trace(
                        f"HTTP Response: {method} {url} | Status: {response.status_code}",
                        extra={"event_data": {
                            "event": "http_response",
                            "library": "httpx_async",
                            "method": method,
                            "url": url,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms,
                            "headers": resp_headers,
                            "body": str(resp_body)[:2000] if resp_body else None
                        }}
                    )
                    return response
                except Exception as e:
                    duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                    logger.error(
                        f"HTTP Request Failed: {method} {url} | Error: {str(e)}",
                        extra={"event_data": {
                            "event": "http_error",
                            "library": "httpx_async",
                            "method": method,
                            "url": url,
                            "duration_ms": duration_ms,
                            "error": str(e)
                        }}
                    )
                    raise
            new_async_send._is_patched = True
            httpx.AsyncClient.send = new_async_send
    except ImportError:
        pass

def setup_exhaustive_logging(log_file_path: str):
    patch_network_libraries()
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
