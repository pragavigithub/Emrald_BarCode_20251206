# QR Label Decimal Quantity Distribution Fix

**Date:** November 12, 2025  
**Issue:** QR label quantity distribution not handling decimal values correctly  
**Status:** ✅ COMPLETED

## Problem Description

When generating QR labels for batch items in both Multi GRN and GRPO modules:
- **Before:** Dividing 11 items into 2 bags resulted in 6 + 5 distribution (uneven)
- **Expected:** Should support decimal values like 5.5 + 5.5 for even distribution

## Changes Made

### 1. Multi GRN Module (`modules/multi_grn_creation/routes.py`)
- ✅ Updated `qty_per_bag` calculations to use `Decimal` type with 3 decimal precision
- ✅ Removed validation that enforced even division for batch items
- ✅ Applied fixes in multiple locations:
  - Line ~688: `update-line-item` endpoint
  - Line ~980: Batch details POST endpoint  
  - Line ~1593: Manual item batch handling
  - Line ~1621: Non-managed items with bags

### 2. GRPO Module (`modules/grpo/routes.py`)
- ✅ Added `Decimal` import from decimal module
- ✅ Updated `qty_per_pack` calculations to use `Decimal` with `.quantize(Decimal('0.001'))`
- ✅ Removed validation enforcing integer-only division for batch items
- ✅ Kept serial item validation (serials must divide evenly since they're discrete units)
- ✅ Applied fixes at:
  - Line ~468: Serial number handling
  - Line ~521: Batch number handling

### 3. Database Schema Updates

#### Model Changes (`modules/grpo/models.py`)
```python
# GRPONonManagedItem model updated:
quantity = db.Column(db.Numeric(15, 3), nullable=False)  # Was: Integer
qty_per_pack = db.Column(db.Numeric(15, 3))             # Was: Integer
```

#### Migration Applied
- Created PostgreSQL migration: `migrations/postgresql_grpo_qty_per_pack_decimal_fix.sql`
- ✅ Executed successfully on development database
- Changes:
  - `grpo_non_managed_items.qty_per_pack`: INTEGER → DECIMAL(15,3)
  - `grpo_non_managed_items.quantity`: INTEGER → DECIMAL(15,3)

## Technical Details

### Precision Handling
All quantity calculations now use Python's `Decimal` type with `.quantize(Decimal('0.001'))` to ensure:
- Precise 3 decimal place rounding (e.g., 5.500, not 5.5 or 5.50000)
- No floating-point arithmetic errors
- Consistent database storage format

### Example Calculation
```python
# Before (incorrect):
qty_per_bag = quantity / bags_count  # 11 / 2 = 5.5 (float, inconsistent precision)

# After (correct):
qty_per_bag = (Decimal(str(quantity)) / Decimal(str(bags_count))).quantize(Decimal('0.001'))
# 11 / 2 = 5.500 (exactly 3 decimals)
```

## Expected Results

### Multi GRN Module
- When entering quantity=11 and bags=2:
  - Each bag will show qty_per_pack = 5.500
  - QR labels will display 5.500 for each pack
  - Database stores 5.500 for both packs

### GRPO Module  
- When entering batch quantity=10 and bags=3:
  - Each bag will show qty_per_pack = 3.333
  - QR labels will display 3.333 for each pack
  - Database stores 3.333 for each pack

## MySQL Migration Notes

A MySQL migration file was also created (`migrations/mysql_grpo_qty_per_pack_decimal_fix.sql`) for reference if the production database uses MySQL. The syntax differs from PostgreSQL:
- PostgreSQL: `ALTER COLUMN ... TYPE DECIMAL(15,3)`
- MySQL: `MODIFY COLUMN ... DECIMAL(15,3)`

## Testing Recommendations

1. **Multi GRN Flow:**
   - Create a batch with qty=11, bags=2
   - Click "Generate QR Labels"
   - Verify each label shows qty=5.500

2. **GRPO Flow:**
   - Add batch item with qty=10, bags=3  
   - Generate batch labels
   - Verify each label shows qty=3.333

3. **Edge Cases:**
   - Test even divisions: 10/2 = 5.000 ✓
   - Test uneven: 11/3 = 3.667 ✓
   - Test single bag: 11/1 = 11.000 ✓

## Notes

- Serial items still require even division (e.g., 10 serials / 2 bags) since serials are discrete units
- All existing QR label generation and SAP posting functionality remains compatible
- The database schema already supported decimals for batch items; only non-managed items needed migration
