# QC Dashboard Endpoint Fixes

**Date**: 2025-11-13  
**Type**: Bug Fix  
**Component**: QC Dashboard Template  

## Issue
The QC Dashboard was throwing `BuildError` when trying to render review links for Direct Inventory Transfer, Sales Delivery, and Multi GRN modules.

### Error Details
```
werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'direct_inventory_transfer.transfer_detail' with values ['transfer_id']. Did you mean 'direct_inventory_transfer.detail' instead?

werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'sales_delivery.delivery_detail' with values ['delivery_id']. Did you mean 'sales_delivery.detail' instead?

werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'multi_grn.batch_detail' with values ['batch_id']. Did you mean 'multi_grn.view_batch' instead?
```

## Root Cause
The `qc_dashboard.html` template was using incorrect endpoint names that didn't match the actual endpoint definitions in the blueprints.

## Changes Made

### File: `templates/qc_dashboard.html`

#### 1. Direct Inventory Transfer (Line 268)
**Before:**
```html
<a href="{{ url_for('direct_inventory_transfer.transfer_detail', transfer_id=transfer.id) }}" class="btn btn-sm btn-outline-primary">
```

**After:**
```html
<a href="{{ url_for('direct_inventory_transfer.detail', transfer_id=transfer.id) }}" class="btn btn-sm btn-outline-primary">
```

#### 2. Sales Delivery (Line 347)
**Before:**
```html
<a href="{{ url_for('sales_delivery.delivery_detail', delivery_id=delivery.id) }}" class="btn btn-sm btn-outline-primary">
```

**After:**
```html
<a href="{{ url_for('sales_delivery.detail', delivery_id=delivery.id) }}" class="btn btn-sm btn-outline-primary">
```

#### 3. Multi GRN (Line 422)
**Before:**
```html
<a href="{{ url_for('multi_grn.batch_detail', batch_id=batch.id) }}" class="btn btn-sm btn-outline-primary">
```

**After:**
```html
<a href="{{ url_for('multi_grn.view_batch', batch_id=batch.id) }}" class="btn btn-sm btn-outline-primary">
```

## Endpoint Mapping Verified
All endpoints now correctly match their blueprint definitions:
- **Direct Inventory Transfer**: `direct_inventory_transfer.detail` (modules/direct_inventory_transfer/routes.py)
- **Sales Delivery**: `sales_delivery.detail` (modules/sales_delivery/routes.py)
- **Multi GRN**: `multi_grn.view_batch` (modules/multi_grn_creation/routes.py)

## Impact
- Fixes all 500 errors on the QC Dashboard page
- Allows QC approvers to properly review all pending requests:
  - Direct Inventory Transfer requests
  - Sales Delivery requests
  - Multi GRN batch requests
- No database schema changes required

## Testing
- Application restarted and verified responding with HTTP 200
- All endpoint names verified against actual blueprint route definitions

## Notes
This was a template-only fix and did not require any database migrations.
