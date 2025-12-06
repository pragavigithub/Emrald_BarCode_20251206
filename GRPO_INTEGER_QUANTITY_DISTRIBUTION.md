# GRPO Integer Quantity Distribution Implementation

## Date: November 14, 2025

## Summary
Modified the GRPO module to ensure that quantity per pack is always an integer value (no decimals). When quantities are not evenly divisible, the first QR label receives the highest quantity, and the remaining quantity is evenly distributed across other labels.

## Changes Made

### 1. Batch Number Handling (Batch-Managed Items)
**File**: `modules/grpo/routes.py` (lines 506-578)

**Previous Behavior**:
- Created ONE batch record with `qty_per_pack` (decimal allowed, e.g., 3.667)
- `no_of_packs` stored the total number of packs
- QR label generation looped to create multiple labels from single batch record

**New Behavior**:
- Creates MULTIPLE batch records (one per pack)
- Each record has integer `quantity` (no decimals)
- First pack gets highest quantity (base + remainder)
- Each record has `no_of_packs=1` (represents individual pack)

**Example**:
```
Total Quantity: 11
Number of Packs: 3

Distribution:
- Pack 1: quantity=4 (base 3 + remainder 2)
- Pack 2: quantity=3 (base only)
- Pack 3: quantity=3 (base only)
```

**Database Impact**:
- More `GRPOBatchNumber` records (N records instead of 1, where N = number of packs)
- Each record represents exactly one physical pack
- Better tracking granularity

### 2. Non-Managed Items Handling
**File**: `modules/grpo/routes.py` (lines 614-662)

**Previous Behavior**:
- Calculated `qty_per_pack` as decimal division
- All packs had same quantity (potentially decimal)

**New Behavior**:
- Integer division with remainder distribution
- First pack gets extra quantity
- Each pack record has `no_of_packs=1`

**Example**:
```
Total Quantity: 11
Number of Bags: 3

Distribution:
- Pack 1: 4 units
- Pack 2: 3 units
- Pack 3: 3 units
```

### 3. QR Label Generation
**File**: `modules/grpo/routes.py` (lines 1306-1365)

**Previous Behavior**:
- Looped through packs based on `no_of_packs` field
- Generated multiple labels from single batch record
- Used decimal `qty_per_pack` value

**New Behavior**:
- Groups batch records by `batch_number`
- Sorts by `base_line_number` to maintain order
- Uses integer `quantity` directly from each record
- Each batch record = one QR label

**QR Data Changes**:
- `'Qty'`: Now always integer (was decimal)
- Pack sequence: "1 of 3", "2 of 3", "3 of 3"
- First pack QR shows highest quantity

## Database Schema

### GRPOBatchNumber Table
No schema changes required. Existing fields support the new logic:

```sql
- quantity: NUMERIC(15, 3) -- Now stores integer per pack
- qty_per_pack: NUMERIC(15, 3) -- Same as quantity for individual packs
- no_of_packs: INTEGER -- Always 1 for new records
- base_line_number: INTEGER -- Used for sorting (maintains order)
- grn_number: VARCHAR(50) -- Unique per pack
```

### GRPONonManagedItem Table
No schema changes required:

```sql
- quantity: NUMERIC(15, 3) -- Now stores integer per pack
- qty_per_pack: NUMERIC(15, 3) -- Same as quantity
- no_of_packs: INTEGER -- Always 1 for new records
- pack_number: INTEGER -- Pack sequence (1, 2, 3, ...)
```

## Migration Notes

### For MySQL Users
**No migration script required** - The changes are in application logic only. The database schema already supports integer quantities.

**Existing Data**:
- Old records (with decimal qty_per_pack and no_of_packs>1) will continue to work
- New records will use integer distribution
- QR label generation handles both old and new formats

**Cleanup (Optional)**:
If you want to convert old records to new format:
```sql
-- This is OPTIONAL and only for consistency
-- Old records will still generate correct QR labels
-- Contact your system administrator before running
```

### For PostgreSQL Users
Same as MySQL - no migration needed. Schema supports the changes.

## Testing Recommendations

### Test Case 1: Evenly Divisible
- Total Quantity: 12
- Number of Packs: 3
- Expected: 4, 4, 4

### Test Case 2: Not Evenly Divisible
- Total Quantity: 11
- Number of Packs: 3
- Expected: 5, 3, 3 (first pack gets remainder)

### Test Case 3: Large Remainder
- Total Quantity: 10
- Number of Packs: 3
- Expected: 4, 3, 3

### Test Case 4: Single Pack
- Total Quantity: 100
- Number of Packs: 1
- Expected: 100

## Backwards Compatibility

The new QR label generation logic handles both:
1. **New records**: Multiple batch records with `no_of_packs=1`
2. **Old records**: Single batch record with `no_of_packs>1`

This ensures existing QR labels continue to work while new ones use integer distribution.

## Benefits

1. **Compliance**: No decimal quantities on physical packs
2. **Accuracy**: First pack clearly identified with highest quantity
3. **Clarity**: QR labels show exact integer quantities
4. **Traceability**: Each pack has its own database record
5. **Consistency**: Same logic for batch and non-managed items
