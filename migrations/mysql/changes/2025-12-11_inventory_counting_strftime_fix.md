# Inventory Counting strftime Fix

**Date**: 2025-12-11  
**Issue**: Error in get_local_invcnt_details API: 'str' object has no attribute 'strftime'

## Problem

The `/api/get-local-invcnt-details` endpoint was calling `.strftime()` directly on `loaded_at` and `last_updated_at` fields, assuming they were always datetime objects. However, these fields could be stored as strings in certain database scenarios.

## Solution

Added a `safe_format_datetime()` helper function that:
1. Returns `None` if value is None
2. Returns the string as-is if value is already a string
3. Calls `.strftime()` only on actual datetime objects
4. Falls back to `str()` conversion on any other type

## Code Changes (routes.py)

**Added helper function:**
```python
def safe_format_datetime(value):
    """Safely format datetime - handles both datetime objects and strings"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.strftime('%Y-%m-%d %H:%M:%S')
    except (AttributeError, TypeError):
        return str(value) if value else None
```

**Updated usage:**
```python
'LoadedAt': safe_format_datetime(local_doc.loaded_at),
'LastUpdatedAt': safe_format_datetime(local_doc.last_updated_at),
```

## Database Changes

No database schema changes required - this is a code-only fix.
