# Multi GRN Single Batch Generation Fix

**Date:** November 17, 2025  
**Type:** Logic Change (No Schema Changes)  
**Module:** Multi GRN Creation

## Summary
Fixed Multi GRN batch generation to create a SINGLE batch entry in the SAP JSON payload regardless of the "Number of Packs/Bags" value. The number of packs is now used exclusively for QR label generation, not for splitting batches.

## Problem
When users entered "Number of Packs/Bags = 2", the system was:
1. Creating 2 separate `MultiGRNBatchDetails` records with split quantities
2. Generating JSON with multiple batch entries (e.g., qty 3 + qty 2 instead of qty 5)
3. This caused incorrect batch structures in SAP

## Solution

### 1. Batch Generation Logic Changes (update_line_item endpoint)
**File:** `modules/multi_grn_creation/routes.py` (lines 1035-1083)

**Before:**
- Created multiple `MultiGRNBatchDetails` records (one per pack)
- Split quantity across packs: Pack 1 gets (base + remainder), others get base
- Example: 5 items, 2 packs → 2 records (qty 3, qty 2)

**After:**
- Creates SINGLE `MultiGRNBatchDetails` record with full quantity
- Stores `no_of_packs` and `qty_per_pack` for QR label generation only
- Example: 5 items, 2 packs → 1 record (qty 5, no_of_packs=2)

### 1b. Batch Generation for Non-Managed Items (add_item_to_batch endpoint)
**File:** `modules/multi_grn_creation/routes.py` (lines 2015-2032)

**Before:**
- Created multiple `MultiGRNBatchDetails` records in a loop (one per pack)
- Each record had split quantity
- Example: 10 items, 2 packs → 2 records (qty 5, qty 5)

**After:**
- Creates SINGLE `MultiGRNBatchDetails` record with full quantity
- Stores `no_of_packs` for QR label generation only
- Example: 10 items, 2 packs → 1 record (qty 10, no_of_packs=2)
- Added logging to track creation

### 2. QR Label Generation Changes
**File:** `modules/multi_grn_creation/routes.py` (lines 1656-1759)

**Changes:**
- Updated both 'batch' and 'regular' label types
- Now reads single batch_detail record
- Generates multiple labels based on `batch_detail.no_of_packs`
- Each label shows correct pack numbering: "1 of 2", "2 of 2"

### 3. QR Label Display Enhancement
**File:** `modules/multi_grn_creation/templates/multi_grn/step3_detail.html` (line 633)

**Added:**
```javascript
${label.item_code ? `<tr><td class="fw-bold py-1">Item Code:</td><td class="py-1">${label.item_code}</td></tr>` : ''}
```

## Impact

### JSON Structure Changes
**Before (Number of Packs = 2):**
```json
"BatchNumbers": [
    {"BatchNumber": "20251117-BatchItem_-1", "Quantity": 3.0},
    {"BatchNumber": "20251117-BatchItem_-2", "Quantity": 2.0}
]
```

**After (Number of Packs = 2):**
```json
"BatchNumbers": [
    {"BatchNumber": "20251117-BatchItem_-1", "Quantity": 5.0}
]
```

### QR Labels
- **Before:** Missing ItemCode field
- **After:** Displays ItemCode on all QR labels

### Database Impact
- **Schema:** No changes required
- **Existing Data:** Compatible (uses same fields: `no_of_packs`, `qty_per_pack`)
- **Migration:** Not needed

## Testing Recommendations
1. Test with various `no_of_packs` values (1, 2, 5, etc.)
2. Verify JSON payload has single batch entry with full quantity
3. Verify QR labels generate correctly (correct count and numbering)
4. Verify ItemCode appears on all QR labels
5. Test with batch-managed, serial-managed, and standard items

## Files Modified
- `modules/multi_grn_creation/routes.py`
- `modules/multi_grn_creation/templates/multi_grn/step3_detail.html`

## Backward Compatibility
✅ Fully compatible - uses existing database schema
✅ No data migration required
✅ Existing QR label templates work with new structure
