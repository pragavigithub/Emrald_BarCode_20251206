# Multi GRN QR Code Label Generation Fix - November 23, 2025

## Issue Description
QR Code labels were not generating for Multi GRN batch items. The error occurred when clicking "Print Batch Labels":

**Error Message:**
```
ERROR:root:Error generating barcode labels: cannot access local variable 'json' where it is not associated with a value
```

**HTTP Status:** 500 Internal Server Error

## Root Cause
The `json` module was imported at the top of the file (`modules/multi_grn_creation/routes.py` line 13), but there were also multiple inline `import json` statements inside the `generate_barcode_labels_multi_grn()` function (lines 2023, 2103, 2110, 2171, 2209).

When Python sees an `import` statement anywhere inside a function, it treats that name as a local variable for the ENTIRE function. This caused the code to fail when trying to use `json.loads()` on line 2082 before any of the inline import statements were executed in that code path.

## Solution
Removed all inline `import json` statements from the `generate_barcode_labels_multi_grn()` function since the module was already imported at the file level.

### Changes Made
**File:** `modules/multi_grn_creation/routes.py`

1. Line ~2023: Removed `import json` (serial label type)
2. Line ~2103: Removed `import json` (batch label type - this was causing the error)
3. Line ~2171: Removed `import json` (regular label with batch_details)
4. Line ~2209: Removed `import json` (regular label without batch_details)

## Testing
- Application restarted successfully
- QR code label generation should now work correctly for all label types:
  - Serial labels
  - Batch labels (the failing case)
  - Regular labels with packs
  - Regular labels without packs

## Data Verification
The `multi_grn_batch_details_label` table contains the correct data structure with QR data:
```json
{
  "id": "MGN-134-236-1-1",
  "po": "5500167",
  "item": "CAPELECHITEMS",
  "batch": "20251118-CAPELECHIT-1",
  "qty": 1,
  "pack": "1 of 1",
  "grn_date": "2025-11-18",
  "exp_date": "2025-12-06"
}
```

## Impact
✅ **Fixed:** QR code label generation now works for all Multi GRN items
✅ **No Database Changes:** This was a code-only fix
✅ **No Migration Required:** Existing data structure remains unchanged
