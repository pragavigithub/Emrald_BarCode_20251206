# QC Dashboard DateTime Template Fix

**Date:** November 19, 2025  
**Type:** Template Enhancement + Database Migration  
**Status:** Complete

## Issue

The QC Dashboard was throwing a Jinja2 template error:

```
jinja2.exceptions.UndefinedError: 'str object' has no attribute 'strftime'
```

This occurred when trying to format datetime fields using `.strftime()` in the template:

```jinja2
<small>{{ batch.submitted_at.strftime('%Y-%m-%d %H:%M') if batch.submitted_at else 'N/A' }}</small>
```

## Root Cause

The datetime columns in MySQL were being returned as strings instead of datetime objects by SQLAlchemy. This can happen when:
1. The MySQL column type is not explicitly defined as DATETIME
2. There's a mismatch between the SQLAlchemy model definition and the actual MySQL schema
3. The database was migrated or columns were added without explicit type definitions

## Solution

### 1. Template Enhancement (templates/qc_dashboard.html)

Added a safe Jinja2 macro that can handle both datetime objects and strings:

```jinja2
{% macro format_datetime(dt, format='%Y-%m-%d %H:%M') -%}
    {% if dt %}
        {% if dt is string %}
            {{ dt[:16].replace('T', ' ') if 'T' in dt else dt[:16] }}
        {% else %}
            {{ dt.strftime(format) }}
        {% endif %}
    {% else %}
        N/A
    {% endif %}
{%- endmacro %}
```

### 2. Updated All DateTime Formatting Calls

Replaced all `.strftime()` calls with the safe macro:

**Before:**
```jinja2
{{ batch.submitted_at.strftime('%Y-%m-%d %H:%M') if batch.submitted_at else 'N/A' }}
```

**After:**
```jinja2
{{ format_datetime(batch.submitted_at) }}
```

**Affected Fields:**
- `grpo.updated_at` (line 123)
- `transfer.updated_at` (line 201)
- `transfer.submitted_at` (line 279)
- `delivery.submitted_at` (line 358)
- `batch.submitted_at` (line 433)

### 3. MySQL Migration (2025-11-19_qc_dashboard_datetime_columns_fix.sql)

Created a comprehensive SQL migration to ensure all datetime columns are properly defined as DATETIME type across all QC-related tables:

**Tables Updated:**
- `multi_grn_batches`
  - submitted_at, qc_approved_at, created_at, posted_at, completed_at
- `direct_inventory_transfers`
  - submitted_at, qc_approved_at, created_at, updated_at
- `sales_deliveries`
  - submitted_at, qc_approved_at, created_at, updated_at
- `grpo_master`
  - created_at, updated_at, grn_date
- `inventory_transfer_master`
  - created_at, updated_at

## Benefits

1. **Backward Compatible:** The template macro handles both datetime objects (from PostgreSQL/SQLite on Replit) and strings (from older MySQL schemas)
2. **Future-Proof:** MySQL migration ensures correct column types going forward
3. **No Data Loss:** The ALTER TABLE statements preserve existing data while enforcing correct types
4. **Better Documentation:** Added column comments for clarity
5. **Consistent Behavior:** All datetime fields now work the same way across different database backends

## Testing

1. ✅ Template renders without errors when datetime fields are strings
2. ✅ Template renders without errors when datetime fields are datetime objects
3. ✅ NULL/None datetime values display as "N/A"
4. ✅ Datetime formatting is consistent across all sections of the dashboard

## Files Modified

- `templates/qc_dashboard.html` - Added safe datetime formatting macro and updated all datetime field rendering
- `migrations/mysql/changes/2025-11-19_qc_dashboard_datetime_columns_fix.sql` - Database migration to fix column types

## No PostgreSQL Changes Required

The PostgreSQL database on Replit already has correct DATETIME column types, so no migration is needed for the cloud environment. This fix only applies to local MySQL installations.
