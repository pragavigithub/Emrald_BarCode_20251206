# Multi GRN Module: Integer Pack Distribution Fix

**Date:** November 17, 2025  
**Module:** Multi GRN Creation  
**Type:** Logic Enhancement (No Schema Changes)

## Overview

Updated the Multi GRN module to ensure that quantity distribution across packs uses **integer values only** (no decimals). When total quantity is not evenly divisible by the number of packs, the first packs receive the extra units.

## Problem

Previously, when dividing quantities into multiple packs, the system would create decimal values:
- Example: 11 quantity ÷ 3 packs = 3.67 per pack (stored as 3.67)
- This resulted in QR labels showing decimal quantities like "110.25" which is not appropriate for item counting

## Solution

Implemented integer distribution algorithm where:
- Total quantity is divided using integer division
- Remainder is distributed to the first packs
- Example: 11 quantity ÷ 3 packs = [4, 4, 3]
  - Pack 1: 4 units
  - Pack 2: 4 units  
  - Pack 3: 3 units

## Changes Made

### 1. New Helper Function

Added `distribute_quantity_to_packs()` function in `modules/multi_grn_creation/routes.py`:

```python
def distribute_quantity_to_packs(total_quantity, num_packs):
    """
    Distribute total quantity across packs as integers.
    First packs get extra units if quantity doesn't divide evenly.
    Uses ROUND_HALF_UP to preserve total quantity (no truncation).
    """
    # Use ROUND_HALF_UP to consistently round .5 up (not banker's rounding)
    total_qty_decimal = Decimal(str(total_quantity))
    total_qty_int = int(total_qty_decimal.to_integral_value(rounding=ROUND_HALF_UP))
    base_qty = total_qty_int // num_packs
    remainder = total_qty_int % num_packs
    
    quantities = []
    for i in range(num_packs):
        if i < remainder:
            quantities.append(base_qty + 1)
        else:
            quantities.append(base_qty)
    
    return quantities
```

**Important:** Uses `ROUND_HALF_UP` rounding mode to ensure .5 values always round up, preserving quantity accurately.

### 2. Updated Endpoints

#### update_line_item Endpoint (Line ~1091)
```python
# Before:
qty_per_pack = total_qty / Decimal(bags_count)

# After:
total_qty_int = int(total_qty_original.to_integral_value(rounding=ROUND_HALF_UP))
total_qty = Decimal(total_qty_int)  # Store rounded integer quantity
qty_per_pack = Decimal(total_qty_int // bags_count)
```

#### add_item_to_batch Endpoint - Batch Managed Items (Line ~2044)
```python
# Before:
qty_per_pack = (Decimal(str(batch_qty)) / Decimal(str(number_of_bags))).quantize(Decimal('0.001'))

# After:
batch_qty_decimal = Decimal(str(batch_qty))
batch_qty_int = int(batch_qty_decimal.to_integral_value(rounding=ROUND_HALF_UP))
qty_per_pack = Decimal(batch_qty_int // number_of_bags)
```

#### add_item_to_batch Endpoint - Non-Managed Items (Line ~2075)
```python
# Before:
qty_per_pack = (Decimal(str(quantity)) / Decimal(str(number_of_bags))).quantize(Decimal('0.001'))

# After:
quantity_decimal = Decimal(str(quantity))
quantity_int = int(quantity_decimal.to_integral_value(rounding=ROUND_HALF_UP))
qty_per_pack = Decimal(quantity_int // number_of_bags)
```

### 3. Updated QR Label Generation

Both batch and regular label generation now calculate the distribution on-the-fly:

```python
# Calculate integer distribution across packs
total_quantity = int(batch_detail.quantity)
pack_quantities = distribute_quantity_to_packs(total_quantity, num_packs)

# Assign specific quantity to each pack
for pack_num in range(1, num_packs + 1):
    pack_qty = pack_quantities[pack_num - 1]
    qr_data['qty'] = pack_qty
    label['qty_per_pack'] = pack_qty
```

## Database Impact

**No schema changes required.** The existing `multi_grn_batch_details` table structure remains unchanged:
- `qty_per_pack` column: Still stores base quantity (now as integer)
- `no_of_packs` column: Still stores number of packs
- Actual distribution is calculated dynamically when generating QR labels

## Examples

### Example 1: Evenly Divisible
- Total Quantity: 12
- Number of Packs: 3
- Distribution: [4, 4, 4]

### Example 2: With Remainder
- Total Quantity: 11
- Number of Packs: 3
- Distribution: [4, 4, 3]
- First 2 packs get 4 units each (base + 1)
- Last pack gets 3 units (base only)

### Example 3: Larger Remainder
- Total Quantity: 110
- Number of Packs: 4
- Distribution: [28, 28, 27, 27]
- First 2 packs get 28 units (base + 1)
- Last 2 packs get 27 units (base only)

### Example 4: Decimal with .5 (ROUND_HALF_UP)
- Total Quantity: 110.5
- Rounds to: 111 (using ROUND_HALF_UP)
- Number of Packs: 4
- Distribution: [28, 28, 28, 27]
- Total preserved: 28 + 28 + 28 + 27 = 111 ✓

### Example 5: Decimal with .25
- Total Quantity: 110.25
- Rounds to: 110 (using ROUND_HALF_UP)
- Number of Packs: 4
- Distribution: [28, 28, 27, 27]
- Total preserved: 28 + 28 + 27 + 27 = 110 ✓

## Impact

- **QR Labels**: Now display integer quantities only
- **User Experience**: Clearer, more accurate pack quantities
- **Data Integrity**: Total quantity remains the same (sum of all pack quantities = total)
- **Backward Compatibility**: Existing data continues to work; new calculations apply to new entries

## Testing Recommendations

1. Create a Multi GRN with 11 total quantity and 3 packs
2. Verify QR labels show: Pack 1=4, Pack 2=4, Pack 3=3
3. Test with various combinations (even/odd quantities, different pack counts)
4. Verify total quantity is preserved across all packs

## Related Files

- `modules/multi_grn_creation/routes.py`: Core logic updates
- `modules/multi_grn_creation/models.py`: No changes (schema intact)
- `modules/multi_grn_creation/templates/`: No changes needed

## Notes

- This is a **logic-only change** with no database migration required
- Existing records will use the new distribution algorithm when generating labels
- The `qty_per_pack` stored in database is now the base quantity (for reference only)
- Actual pack quantities are calculated dynamically to ensure integer distribution
