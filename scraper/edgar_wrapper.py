"""
edgar_wrapper.py - Wrapper module for edgar package to make it Lambda-compatible
"""

import os
import time
import logging
from pathlib import Path
import httpx
from httpx import ConnectTimeout

### EDGARTOOLS ###
# Create the tmp directory for edgar
os.makedirs("/tmp/edgar", exist_ok=True)

# Set environment variables to redirect edgar's file operations
os.environ["EDGAR_DATA_DIR"] = "/tmp/edgar"
os.environ["HOME"] = "/tmp/home"

# Create a directory for home
os.makedirs("/tmp/home", exist_ok=True)

# Now monkey patch the os.makedirs function
original_makedirs = os.makedirs


def patched_makedirs(path, mode=0o777, exist_ok=False): # type: ignore
    """Patch makedirs to redirect any problematic paths to /tmp"""
    # Convert Path objects to strings for comparison
    path_str = str(path) if hasattr(path, "__fspath__") else path

    if isinstance(path_str, str) and path_str.startswith("/home"):
        # Redirect to /tmp/home
        new_path = "/tmp" + path_str
        return original_makedirs(new_path, mode, exist_ok)
    return original_makedirs(path, mode, exist_ok)


# Apply the monkey patch
os.makedirs = patched_makedirs

# Now import the edgar package components
from edgar import Company, set_identity, MultiFinancials

# Export the components we need
__all__ = ["Company", "set_identity", "MultiFinancials"]

# Patch HTTPX for better reliability
# The correct way to patch httpx is to patch the Client.request method
original_httpx_request = httpx.Client.request


def patched_httpx_request(self, *args, **kwargs): # type: ignore
    # Set longer timeout
    if "timeout" not in kwargs:
        kwargs["timeout"] = 45.0

    # Add retry logic
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return original_httpx_request(self, *args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if attempt < max_retries - 1 and any(
                x in error_msg for x in ["timeout", "connection", "network"]
            ):
                wait = (attempt + 1) * 5
                logging.warning(f"SEC API request failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


# Apply the patch
httpx.Client.request = patched_httpx_request # type: ignore
