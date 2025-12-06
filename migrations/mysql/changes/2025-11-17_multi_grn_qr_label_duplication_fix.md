# Multi GRN QR Label Duplication Fix

**Date**: 2025-11-17  
**Type**: Bug Fix (No Schema Changes)  
**Module**: Multi GRN Creation  
**Status**: ✅ Applied

## Issue Description

When generating QR labels for Multi GRN batch-managed items, if a user entered "Number of Packs/Bags" as 2, the system was generating 4 QR labels instead of 2.

### Root Cause

In the `generate_barcode_labels_multi_grn()` function (`modules/multi_grn_creation/routes.py`), the batch label generation logic had a nested loop:

```python
for batch_detail in batch_details:  # Loop 1: Each batch_detail (2 records when bags=2)
    num_packs = batch_detail.no_of_packs or 1  # This was also set to 2
    for pack_idx in range(1, num_packs + 1):  # Loop 2: Creating labels per pack
        # Create label
```

This resulted in: **2 batch_details × 2 num_packs = 4 labels**

### Expected Behavior

Each `batch_detail` record already represents ONE pack/bag. When "Number of Bags" is 2:
- 2 `batch_detail` records are created (one per bag)
- Each should generate exactly ONE QR label
- **Result: 2 labels total**

## Fix Applied

### Code Changes

**File**: `modules/multi_grn_creation/routes.py`  
**Lines**: 1649-1705

#### Before (Buggy Code)
```python
for batch_detail in batch_details:
    num_packs = batch_detail.no_of_packs or 1
    
    for pack_idx in range(1, num_packs + 1):  # ❌ Creates multiple labels per batch_detail
        batch_grn = batch_detail.grn_number or doc_number
        # ... create label ...
        labels.append(label)
        label_counter += 1
```

#### After (Fixed Code)
```python
label_counter = 1
total_packs = len(batch_details)  # ✅ Total is based on number of batch_detail records

for batch_detail in batch_details:
    batch_grn = batch_detail.grn_number or doc_number
    # ... create ONE label per batch_detail ...
    label = {
        'sequence': label_counter,
        'total': total_packs,  # ✅ Correct total count
        'pack_text': f"{label_counter} of {total_packs}",
        # ... other fields ...
    }
    labels.append(label)
    label_counter += 1
```

### Changes Summary

1. **Removed inner loop**: No longer iterating over `num_packs` for each `batch_detail`
2. **Calculate total correctly**: `total_packs = len(batch_details)` instead of using `num_packs`
3. **One label per batch_detail**: Each batch_detail generates exactly one QR label
4. **Correct pack numbering**: Labels now show "1 of 2", "2 of 2" instead of duplicates

## Testing

### Test Scenario
1. Create Multi GRN with a batch-managed item
2. Set "Number of Packs/Bags" = 2
3. Set "Quantity" = 10
4. Generate QR Labels

### Expected Results
- ✅ **2 QR labels** are generated (not 4)
- ✅ Label 1: "1 of 2" with 5 units per pack
- ✅ Label 2: "2 of 2" with 5 units per pack
- ✅ Each label prints on a separate page

## Print Layout Fix

The print CSS was already in place to ensure each label prints on a separate page:

**File**: `modules/multi_grn_creation/templates/multi_grn/step3_detail.html`  
**Lines**: 749-751

```css
@media print {
    .print-page-break {
        page-break-after: always;
        page-break-inside: avoid;
    }
}
```

Each label div has the class `print-page-break` to trigger page breaks during printing.

## Impact

- **Users Affected**: All users generating QR labels for batch-managed items in Multi GRN
- **Database Schema**: No changes required
- **Backward Compatibility**: Fully compatible with existing data
- **Performance**: Improved (fewer labels generated = faster processing)

## Related Documentation

- `MULTI_GRN_QR_LABELS_FIX.md` - Original QR label implementation
- `GRPO_INTEGER_QUANTITY_DISTRIBUTION.md` - Quantity distribution logic
- `INDIVIDUAL_BARCODE_LABELS_GUIDE.md` - Label generation guidelines

## Notes

- This fix aligns batch label generation with the logic used for regular/standard items
- No migration SQL file needed (code-only fix)
- The fix applies to batch-managed items only
- Serial-managed items and non-managed items were not affected by this bug
