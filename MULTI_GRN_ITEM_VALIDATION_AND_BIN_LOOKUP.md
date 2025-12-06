# Multi GRN: Item Validation and Bin Location Lookup Enhancement

## Overview
Enhanced Multi GRN Module with dynamic SAP item validation and bin location lookup to ensure correct JSON structure when posting to SAP B1 Service Layer.

## Date: November 14, 2025
## Status: ✅ FIXED - Critical bugs resolved

## Bug Fixes Applied

### Critical Bug #1: Wrong Field Names in Manual Item Addition (FIXED ✅)
**Location:** `modules/multi_grn_creation/routes.py` lines 1752-1753
**Problem:** Code was looking for `batch_required` and `serial_required` in SAP validation response, but the actual response contains `batch_managed` and `serial_managed`.
**Impact:** All manually added items were incorrectly classified as standard items (batch_required='N', serial_required='N').
**Fix:** Changed to use correct field names: `batch_managed`, `serial_managed`, and `management_method`.

### Critical Bug #2: Missing SAP Validation for PO Line Items (FIXED ✅)
**Location:** `modules/multi_grn_creation/routes.py` lines 248-260
**Problem:** When selecting items from PO lines, no SAP validation was performed. Fields `batch_required`, `serial_required`, and `manage_method` were never set.
**Impact:** All PO line items lacked proper batch/serial management flags, causing incorrect JSON generation.
**Fix:** Added SAP item validation for every item selected from PO lines, with proper field population.

### Critical Bug #3: Incorrect manage_method Value (FIXED ✅)
**Location:** `modules/multi_grn_creation/routes.py` line 1787
**Problem:** `manage_method` was being set to 'B', 'S', or 'N' instead of SAP's actual values ('A' for standard, 'R' for quantity-managed).
**Impact:** Quantity-managed items (NonBatch_NonSerialMethod='R') were not generating BatchNumbers section.
**Fix:** Changed to use actual SAP `management_method` value from validation response.

## SAP Item Management Types

### Type 1: Batch-Managed Items (BatchNum='Y')
**SAP Response:**
```json
{
    "BatchNum": "Y",
    "ItemCode": "BatchItem_01",
    "NonBatch_NonSerialMethod": "A",
    "SerialNum": "N"
}
```

**GRN JSON:**
```json
{
    "DocumentLines": [
        {
            "BaseType": 22,
            "BaseEntry": 3673,
            "BaseLine": 1,
            "ItemCode": "BatchItem_01",
            "Quantity": 10.0,
            "WarehouseCode": "7000-FG",
            "DocumentLinesBinAllocations": [
                {
                    "BinAbsEntry": "251",
                    "Quantity": 10.0
                }
            ],
            "BatchNumbers": [
                {
                    "BatchNumber": "20251112-BatchItem_-1",
                    "Quantity": 1.0,
                    "ManufacturerSerialNumber": "MFG-SN-002",
                    "InternalSerialNumber": "INT-SN-002",
                    "ExpiryDate": "2025-10-18T00:00:00Z"
                }
            ]
        }
    ]
}
```

**Logic:** `batch_required='Y'` → **Include BatchNumbers section**

---

### Type 2: Standard Items (BatchNum='N', SerialNum='N', Method='A')
**SAP Response:**
```json
{
    "BatchNum": "N",
    "ItemCode": "Non_Sr_Bt",
    "NonBatch_NonSerialMethod": "A",
    "SerialNum": "N"
}
```

**GRN JSON:**
```json
{
    "DocumentLines": [
        {
            "BaseType": 22,
            "BaseEntry": 3673,
            "BaseLine": 0,
            "ItemCode": "Non_Sr_Bt",
            "Quantity": 10.0,
            "WarehouseCode": "7000-FG",
            "DocumentLinesBinAllocations": [
                {
                    "BinAbsEntry": "251",
                    "Quantity": 10.0
                }
            ]
        }
    ]
}
```

**Logic:** `batch_required='N'` AND `serial_required='N'` AND `manage_method='A'` → **Exclude BatchNumbers and SerialNumbers**

---

### Type 3: Serial-Managed Items (SerialNum='Y')
**SAP Response:**
```json
{
    "BatchNum": "N",
    "ItemCode": "SerialItem_01",
    "NonBatch_NonSerialMethod": "A",
    "SerialNum": "Y"
}
```

**GRN JSON:**
```json
{
    "DocumentLines": [
        {
            "BaseType": 22,
            "BaseEntry": 3673,
            "BaseLine": 2,
            "ItemCode": "SerialItem_01",
            "Quantity": 5.0,
            "WarehouseCode": "7000-FG",
            "SerialNumbers": [
                {
                    "InternalSerialNumber": "SN-001",
                    "Quantity": 1.0,
                    "BaseLineNumber": 2
                }
            ]
        }
    ]
}
```

**Logic:** `serial_required='Y'` → **Include SerialNumbers section** (uses `elif` so BatchNumbers is excluded)

---

### Type 4: Quantity-Managed Items (BatchNum='N', SerialNum='N', Method='R')
**SAP Response:**
```json
{
    "BatchNum": "N",
    "ItemCode": "QuantityItem_01",
    "NonBatch_NonSerialMethod": "R",
    "SerialNum": "N"
}
```

**GRN JSON:**
```json
{
    "DocumentLines": [
        {
            "ItemCode": "QuantityItem_01",
            "Quantity": 100.0,
            "WarehouseCode": "7000-FG",
            "BatchNumbers": [
                {
                    "BatchNumber": "LOT-2025-001",
                    "Quantity": 100.0
                }
            ]
        }
    ]
}
```

**Logic:** `manage_method='R'` → **Include BatchNumbers for lot consolidation**

---

## Implementation Details

### 1. SAP Item Validation Query
**Endpoint:** `POST /b1s/v1/SQLQueries('ItemCode_Batch_Serial_Val')/List`

**Request:**
```json
{
    "ParamList": "itemCode='BatchItem_01'"
}
```

**Response:**
```json
{
    "value": [
        {
            "ItemCode": "BatchItem_01",
            "BatchNum": "Y",
            "SerialNum": "N",
            "NonBatch_NonSerialMethod": "A"
        }
    ]
}
```

**Service Method:** `SAPMultiGRNService.validate_item_code(item_code)`
- Located in: `modules/multi_grn_creation/services.py` (lines 286-349)
- Returns: `{success, item_code, batch_managed, serial_managed, inventory_type, management_method}`

---

### 2. Bin Location Lookup Query
**Endpoint:** `GET /b1s/v1/BinLocations?$filter=BinCode eq 'BIN_CODE'`

**Example Request:**
```
GET /b1s/v1/BinLocations?$filter=BinCode eq '7000-FG-A101'
```

**Response:**
```json
{
    "value": [
        {
            "AbsEntry": 251,
            "Warehouse": "7000-FG",
            "BinCode": "7000-FG-A101",
            "Sublevel1": "A101",
            "Sublevel2": null,
            "Sublevel3": null,
            "Sublevel4": null
        }
    ]
}
```

**Service Method:** `SAPMultiGRNService.get_bin_abs_entry(bin_code)`
- Located in: `modules/multi_grn_creation/services.py` (lines 469-521)
- Returns: `{success, abs_entry, warehouse, bin_code, bin_data}`

---

## Conditional BatchNumbers/SerialNumbers Logic

### Code Location
`modules/multi_grn_creation/routes.py`:
- **create_step5_post:** Lines 360-407
- **approve_batch (QC approval):** Lines 562-609

### Condition Logic
```python
# BatchNumbers: Include if batch-managed OR quantity-managed
if line.batch_details and (line.batch_required == 'Y' or line.manage_method == 'R'):
    doc_line['BatchNumbers'] = batch_numbers

# SerialNumbers: Include if serial-managed (elif ensures mutual exclusivity)
elif line.serial_details and line.serial_required == 'Y':
    doc_line['SerialNumbers'] = serial_numbers
```

### Truth Table
| batch_required | serial_required | manage_method | BatchNumbers | SerialNumbers | Item Type |
|----------------|-----------------|---------------|--------------|---------------|-----------|
| Y | N | A | ✓ | ✗ | Batch-managed |
| N | Y | A | ✗ | ✓ | Serial-managed |
| N | N | A | ✗ | ✗ | Standard |
| N | N | R | ✓ | ✗ | Quantity-managed |
| Y | Y | A | ✓ | ✗ | Batch & Serial (Batch takes precedence) |

**Key Points:**
1. **Batch-managed items** (`batch_required='Y'`): Always include BatchNumbers
2. **Serial-managed items** (`serial_required='Y'`): Always include SerialNumbers (elif ensures no BatchNumbers)
3. **Standard items** (`batch='N'`, `serial='N'`, `method='A'`): Exclude both sections
4. **Quantity-managed items** (`batch='N'`, `serial='N'`, `method='R'`): Include BatchNumbers for lot consolidation

---

## Database Schema

### MultiGRNLineSelection Model
Located in: `modules/multi_grn_creation/models.py` (lines 67-100)

**Relevant Fields:**
```python
batch_required = db.Column(db.String(1), default='N')    # 'Y' or 'N'
serial_required = db.Column(db.String(1), default='N')   # 'Y' or 'N'
manage_method = db.Column(db.String(1), default='N')     # 'A' (Standard) or 'R' (Quantity-managed)
```

**No Database Changes Required** - Fields already exist!

---

## Usage Examples

### Example 1: Mixed Document (Batch + Standard Items)
```json
{
    "CardCode": "3D SPL",
    "DocDate": "2025-11-14",
    "DocDueDate": "2025-11-14",
    "Comments": "Auto-created from batch 91",
    "NumAtCard": "BATCH-91-PO-252630035",
    "BPL_IDAssignedToInvoice": 5,
    "DocumentLines": [
        {
            "BaseType": 22,
            "BaseEntry": 3673,
            "BaseLine": 1,
            "ItemCode": "BatchItem_01",
            "Quantity": 10.0,
            "WarehouseCode": "7000-FG",
            "DocumentLinesBinAllocations": [
                {"BinAbsEntry": "251", "Quantity": 10.0}
            ],
            "BatchNumbers": [
                {
                    "BatchNumber": "20251112-BatchItem_-1",
                    "Quantity": 1.0,
                    "ExpiryDate": "2025-10-18T00:00:00Z"
                }
            ]
        },
        {
            "BaseType": 22,
            "BaseEntry": 3673,
            "BaseLine": 0,
            "ItemCode": "Non_Sr_Bt",
            "Quantity": 10.0,
            "WarehouseCode": "7000-FG",
            "DocumentLinesBinAllocations": [
                {"BinAbsEntry": "251", "Quantity": 10.0}
            ]
        }
    ]
}
```

---

## Testing Scenarios

### Test Case 1: Batch Item Only
1. Add item with `batch_required='Y'`
2. Add batch details with expiry dates
3. Post to SAP
4. ✅ Verify BatchNumbers section is included

### Test Case 2: Standard Item Only
1. Add item with `batch_required='N'`, `serial_required='N'`, `manage_method='A'`
2. Do NOT add batch/serial details
3. Post to SAP
4. ✅ Verify BatchNumbers and SerialNumbers sections are excluded

### Test Case 3: Serial Item Only
1. Add item with `serial_required='Y'`
2. Add serial number details
3. Post to SAP
4. ✅ Verify SerialNumbers section is included, BatchNumbers excluded

### Test Case 4: Mixed Document
1. Add batch item + standard item in same batch
2. Post to SAP
3. ✅ Verify BatchNumbers only on batch-managed line

---

## Benefits

1. **SAP Compliance:** JSON structure matches SAP B1 Service Layer API requirements exactly
2. **Error Prevention:** Prevents SAP API errors when posting standard items with unnecessary BatchNumbers
3. **Flexibility:** Supports all SAP item management types in a single document
4. **Automatic Detection:** Uses SAP's own validation to determine item types
5. **Backward Compatible:** No database schema changes required

---

## Related Documentation
- `MULTI_GRN_CONDITIONAL_BATCH_NUMBERS.md` - Previous implementation (November 14, 2025)
- `replit.md` - Project architecture and recent changes
- SAP B1 Service Layer API Documentation - BinLocations and SQLQueries endpoints
