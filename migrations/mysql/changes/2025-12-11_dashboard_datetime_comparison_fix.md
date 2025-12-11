# Dashboard Datetime Comparison Fix

**Date**: 2025-12-11  
**Issue**: Dashboard showing error - '<' not supported between instances of 'str' and 'datetime.datetime'

## Problem

The dashboard recent activity section was failing because:
1. SAP Inventory Count entries had `created_at` set as string (ISO format)
2. Other activity entries used `normalize_datetime()` which returns datetime objects
3. When sorting, Python tried to compare strings with datetime objects, causing a TypeError

## Solution

1. Updated SAP Inventory Count section to use `normalize_datetime()` for consistency
2. Updated sorting key to explicitly handle datetime comparison

## Code Changes (routes.py)

**Before:**
```python
for sap_count in recent_sap_counts:
    created_at = sap_count.loaded_at if isinstance(sap_count.loaded_at, str) \
        else sap_count.loaded_at.isoformat() if sap_count.loaded_at else None
    recent_activities.append({
        'type': 'SAP Inventory Count',
        'description': f"Doc: {sap_count.doc_number} (DocEntry: {sap_count.doc_entry})",
        'created_at': created_at,
        'status': sap_count.document_status or 'Open'
    })
```

**After:**
```python
for sap_count in recent_sap_counts:
    recent_activities.append({
        'type': 'SAP Inventory Count',
        'description': f"Doc: {sap_count.doc_number} (DocEntry: {sap_count.doc_entry})",
        'created_at': normalize_datetime(sap_count.loaded_at),
        'status': sap_count.document_status or 'Open'
    })
```

**Sorting Fix:**
```python
# Before
recent_activities = sorted(
    recent_activities, key=lambda x: x['created_at'] or "", reverse=True
)[:10]

# After
recent_activities = sorted(
    recent_activities, key=lambda x: x['created_at'] if isinstance(x['created_at'], datetime) else datetime.min, reverse=True
)[:10]
```

## Database Changes

No database schema changes required - this is a code-only fix.
