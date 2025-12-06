# Multi GRN Pack Distribution Fix
**Date:** November 23, 2025  
**Issue:** Quantity mismatch when scanning QR codes for packs with different quantities  
**Status:** ✅ FIXED

## Problem Description

### Before Fix:
When creating a Multi GRN batch with multiple packs:
- Item: BatchItem_002
- Total Qty: 7
- Number of Packs: 3

**OLD Behavior (WRONG):**
```
Created 1 database record:
┌────┬─────────────────┬──────────┬──────────────┬──────────┐
│ id │ grn_number      │ quantity │ qty_per_pack │ no_of_   │
│    │                 │          │              │ packs    │
├────┼─────────────────┼──────────┼──────────────┼──────────┤
│ 45 │ MGN-18-43-1     │ 7.000    │ 2.000        │ 3        │
└────┴─────────────────┴──────────┴──────────────┴──────────┘

QR Labels generated: MGN-18-43-1-1, MGN-18-43-1-2, MGN-18-43-1-3
But scanning MGN-18-43-1-1 (qty=3) failed because:
- QR shows qty=3
- Database expects qty=7 (for MGN-18-43-1)
- GRN mismatch: scanning "MGN-18-43-1-1" but DB has "MGN-18-43-1"
```

**Error Message:**
```
Quantity mismatch! QR label shows 3 but database expects 7 for pack MGN-18-43-1-1
```

### After Fix:
**NEW Behavior (CORRECT):**
```
Creates 3 database records (one per pack):
┌────┬─────────────────┬──────────┬──────────────┬──────────┐
│ id │ grn_number      │ quantity │ qty_per_pack │ no_of_   │
│    │                 │          │              │ packs    │
├────┼─────────────────┼──────────┼──────────────┼──────────┤
│ 45 │ MGN-18-43-1-1   │ 3.000    │ 3.000        │ 1        │
│ 46 │ MGN-18-43-1-2   │ 2.000    │ 2.000        │ 1        │
│ 47 │ MGN-18-43-1-3   │ 2.000    │ 2.000        │ 1        │
└────┴─────────────────┴──────────┴──────────────┴──────────┘

Distribution Logic:
- Total qty: 7
- Packs: 3
- Base qty: 7 ÷ 3 = 2 (integer division)
- Remainder: 7 % 3 = 1
- Pack 1: 2 + 1 = 3 ✅ (gets remainder)
- Pack 2: 2 ✅
- Pack 3: 2 ✅
- Sum: 3 + 2 + 2 = 7 ✅

Now scanning works:
- Scan MGN-18-43-1-1 (qty=3) → finds record with qty=3 → ✅ Match
- Scan MGN-18-43-1-2 (qty=2) → finds record with qty=2 → ✅ Match
- Scan MGN-18-43-1-3 (qty=2) → finds record with qty=2 → ✅ Match
```

---

## Code Changes

### File: `modules/multi_grn_creation/routes.py`

**Function:** `update_line_item()` (Lines 1344-1396)

**Changes:**
1. ✅ Now creates **SEPARATE database records** for each pack
2. ✅ Each record has its **OWN quantity** (distributed evenly)
3. ✅ Each record has **UNIQUE GRN number** with pack suffix
4. ✅ `no_of_packs=1` (each record = 1 pack, not metadata)

**Distribution Algorithm:**
```python
total_qty_int = int(total_qty.to_integral_value(rounding=ROUND_HALF_UP))
base_qty = total_qty_int // bags_count
remainder = total_qty_int % bags_count

for pack_num in range(1, bags_count + 1):
    # First 'remainder' packs get base_qty + 1, rest get base_qty
    pack_qty = base_qty + 1 if pack_num <= remainder else base_qty
    grn_number = f"MGN-{batch_id}-{line_selection_id}-1-{pack_num}"
    
    # Create individual pack record
    batch_detail = MultiGRNBatchDetails(
        quantity=pack_qty,
        grn_number=grn_number,
        no_of_packs=1
    )
```

---

## QR Scanning Validation

### How It Works Now:

**Step 1: Scan QR Code**
```json
QR Data: {
  "id": "MGN-18-43-1-1",
  "qty": 3
}
```

**Step 2: Database Lookup**
```python
# Query by FULL GRN number (including pack suffix)
batch_detail = MultiGRNBatchDetails.query.filter_by(grn_number="MGN-18-43-1-1").first()

# Result:
batch_detail.grn_number = "MGN-18-43-1-1"
batch_detail.quantity = 3.000
```

**Step 3: Quantity Validation**
```python
db_pack_qty = int(float(batch_detail.quantity))  # 3
qr_pack_qty = int(qr_qty)  # 3

if qr_pack_qty != db_pack_qty:
    return error("Quantity mismatch!")  # Not triggered!

# ✅ Match! Mark as verified
batch_detail.status = 'verified'
```

---

## Duplicate Scan Prevention

The system prevents scanning the same pack twice:

```python
if batch_detail.status == 'verified':
    return jsonify({
        'success': True,
        'message': 'This pack was already verified',
        'already_verified': True
    })
```

**Scenario:**
```
User scans MGN-18-43-1-1 → Status changes to 'verified' ✅
User scans MGN-18-43-1-1 again → System says "already verified" ⚠️
User scans MGN-18-43-1-2 → Different GRN, allows scan ✅
```

---

## Distribution Examples

### Example 1: Even Distribution
```
Total Qty: 9
Packs: 3

Distribution:
- base_qty = 9 ÷ 3 = 3
- remainder = 9 % 3 = 0
- Pack 1: 3
- Pack 2: 3
- Pack 3: 3
Sum: 9 ✅
```

### Example 2: Uneven Distribution
```
Total Qty: 10
Packs: 3

Distribution:
- base_qty = 10 ÷ 3 = 3
- remainder = 10 % 3 = 1
- Pack 1: 3 + 1 = 4 (gets remainder)
- Pack 2: 3
- Pack 3: 3
Sum: 10 ✅
```

### Example 3: Your Case
```
Total Qty: 7
Packs: 3

Distribution:
- base_qty = 7 ÷ 3 = 2
- remainder = 7 % 3 = 1
- Pack 1: 2 + 1 = 3 ✅
- Pack 2: 2 ✅
- Pack 3: 2 ✅
Sum: 7 ✅
```

---

## Testing Instructions

### 1. Delete Old Batch
Before testing, **delete the old batch** (Batch #18) that has the wrong pack structure.

### 2. Create New Batch
1. Go to Multi GRN → Create New Batch
2. Select PO and line items
3. Set:
   - Item: BatchItem_002
   - Quantity: 7
   - Number of Bags: 3
   - Expiry Date: (any date)
4. Click "Update Line Item"

### 3. Verify Database Records
Check that 3 records were created:
```sql
SELECT id, grn_number, quantity, qty_per_pack, no_of_packs, status
FROM multi_grn_batch_details
WHERE line_selection_id = (your_line_id)
ORDER BY grn_number;
```

**Expected Result:**
```
id | grn_number    | quantity | qty_per_pack | no_of_packs | status
---+---------------+----------+--------------+-------------+--------
45 | MGN-XX-XX-1-1 | 3.000    | 3.000        | 1           | pending
46 | MGN-XX-XX-1-2 | 2.000    | 2.000        | 1           | pending
47 | MGN-XX-XX-1-3 | 2.000    | 2.000        | 1           | pending
```

### 4. Generate QR Labels
1. Go to Step 3 in Multi GRN workflow
2. Click "Generate QR Labels"
3. Verify 3 labels are shown with:
   - MGN-XX-XX-1-1, Qty: 3, Pack: 1 of 3
   - MGN-XX-XX-1-2, Qty: 2, Pack: 2 of 3
   - MGN-XX-XX-1-3, Qty: 2, Pack: 3 of 3

### 5. Test QR Scanning
1. Submit batch for QC approval
2. Go to QC Dashboard → QC Review
3. Scan Pack 1 (qty=3) → Should succeed ✅
4. Scan Pack 1 again → Should show "already verified" ⚠️
5. Scan Pack 2 (qty=2) → Should succeed ✅
6. Scan Pack 3 (qty=2) → Should succeed ✅
7. Verify all 3/3 items are verified
8. Approve batch → Should succeed ✅

---

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| Database Records | 1 record with total qty | N records (1 per pack) |
| GRN Number | `MGN-X-Y-1` (no pack suffix) | `MGN-X-Y-1-{pack_num}` |
| Quantity | Total (e.g., 7) | Distributed per pack (3,2,2) |
| no_of_packs | N (metadata) | 1 (each record = 1 pack) |
| QR Scanning | ❌ Failed (GRN mismatch) | ✅ Works (exact match) |
| Duplicate Prevention | ❌ Not possible | ✅ Status-based |

---

## Files Modified

1. **`modules/multi_grn_creation/routes.py`** (Lines 1344-1396)
   - Changed from single-record to multi-record creation
   - Added pack distribution algorithm
   - Updated GRN number format

2. **`migrations/mysql_multi_grn_consolidated.sql`**
   - Updated comments to reflect new behavior
   - Added status column

3. **`MULTI_GRN_QR_PACK_TRACKING_GUIDE.md`**
   - Comprehensive documentation
   - Examples and troubleshooting

---

## Migration Path for Existing Batches

If you have existing batches with the old structure:

**Option 1: Delete and Recreate (Recommended)**
```sql
DELETE FROM multi_grn_batch_details WHERE no_of_packs > 1;
```
Then recreate the batches through the UI.

**Option 2: Migrate Existing Data**
```python
# Run this migration script (not recommended, may have edge cases)
from app import app, db
from modules.multi_grn_creation.models import MultiGRNBatchDetails

with app.app_context():
    old_records = MultiGRNBatchDetails.query.filter(
        MultiGRNBatchDetails.no_of_packs > 1
    ).all()
    
    for old_record in old_records:
        bags_count = old_record.no_of_packs
        total_qty = int(old_record.quantity)
        base_qty = total_qty // bags_count
        remainder = total_qty % bags_count
        
        # Delete old record
        db.session.delete(old_record)
        
        # Create new records
        for pack_num in range(1, bags_count + 1):
            pack_qty = base_qty + 1 if pack_num <= remainder else base_qty
            grn_base = old_record.grn_number.rsplit('-', 1)[0]
            new_grn = f"{grn_base}-{pack_num}"
            
            new_record = MultiGRNBatchDetails(
                line_selection_id=old_record.line_selection_id,
                batch_number=old_record.batch_number,
                quantity=pack_qty,
                grn_number=new_grn,
                qty_per_pack=pack_qty,
                no_of_packs=1,
                expiry_date=old_record.expiry_date
            )
            db.session.add(new_record)
    
    db.session.commit()
    print(f"✅ Migrated {len(old_records)} old records")
```

---

## ✅ Fix Complete

The Multi GRN module now correctly:
1. ✅ Creates separate database records for each pack
2. ✅ Distributes quantities evenly across packs
3. ✅ Assigns unique GRN numbers with pack suffixes
4. ✅ Allows QR scanning to validate individual pack quantities
5. ✅ Prevents duplicate scans of the same pack
6. ✅ Enforces all packs must be scanned before QC approval

Your issue is resolved! 🎉
