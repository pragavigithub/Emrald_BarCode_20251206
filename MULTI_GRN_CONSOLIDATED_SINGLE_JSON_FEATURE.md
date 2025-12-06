# Multi GRN - Consolidated Single JSON Feature

**Date:** November 14, 2025  
**Feature:** Consolidate Multiple Purchase Orders into Single GRN JSON  
**Status:** ✅ Implemented

## Overview

This feature enables the Multi GRN module to consolidate all selected line items from multiple Purchase Orders into a **single GRN JSON** that is posted to SAP B1 as one PurchaseDeliveryNote document.

### Previous Behavior
- Created **one separate GRN per Purchase Order**
- Each PO was posted individually to SAP
- Multiple GRN documents were created (one per PO)

### New Behavior
- Consolidates **all line items from all POs into ONE GRN**
- Single PurchaseDeliveryNote is posted to SAP B1
- All PO links reference the same SAP GRN document number

## Database Schema

**No database schema changes required!** The existing schema already supports this approach:

### Existing Tables Used

#### 1. `multi_grn_batches`
- `total_grns_created` - Now set to 1 (single consolidated GRN)
- `status` - 'completed' or 'failed' (atomic operation)
- `error_log` - Stores any SAP posting errors

#### 2. `multi_grn_po_links`
- `sap_grn_doc_num` - All PO links share the same GRN DocNum
- `sap_grn_doc_entry` - All PO links share the same GRN DocEntry
- `status` - All set to 'posted' or 'failed' together (atomic)
- `error_message` - Stores SAP error if posting fails

#### 3. `multi_grn_line_selections`
- `bin_location` - Can store either:
  - Numeric `BinAbsEntry` (e.g., "968")
  - BinCode string (e.g., "7000-FG-A101")
- If BinCode is provided, the system fetches `BinAbsEntry` from SAP using `BinLocations` API

## MySQL Migration Status

**✅ No migration needed** - Existing schema is sufficient.

If you're using MySQL and want to verify the schema, you can run:

```sql
-- Verify multi_grn_batches table
DESCRIBE multi_grn_batches;

-- Verify multi_grn_po_links table
DESCRIBE multi_grn_po_links;

-- Verify multi_grn_line_selections table
DESCRIBE multi_grn_line_selections;

-- Verify multi_grn_batch_details table (for batch-managed items)
DESCRIBE multi_grn_batch_details;

-- Verify multi_grn_serial_details table (for serial-managed items)
DESCRIBE multi_grn_serial_details;
```

## Key Implementation Changes

### 1. BinAbsEntry Lookup
- System now checks if `bin_location` is numeric (AbsEntry) or string (BinCode)
- If BinCode string, fetches AbsEntry from SAP:
  ```
  GET /b1s/v1/BinLocations?$filter=BinCode eq '7000-FG-A101'
  Response: { "value": [{ "AbsEntry": 968, "BinCode": "7000-FG-A101" }] }
  ```

### 2. DocumentLinesBinAllocations
- Fixed structure to use `DocumentLinesBinAllocations` (not `BinAllocations`)
- Proper `BinAbsEntry` field (numeric)
- Example:
  ```json
  {
    "DocumentLinesBinAllocations": [
      {
        "BinAbsEntry": 968,
        "Quantity": 10.0
      }
    ]
  }
  ```

### 3. Sequential LineNum Across POs
- All lines from all POs are numbered sequentially: 0, 1, 2, 3, ...
- Each line maintains its own `BaseEntry` (PO DocEntry) and `BaseLine` (PO line number)
- Example:
  ```json
  {
    "DocumentLines": [
      {
        "LineNum": 0,
        "BaseType": 22,
        "BaseEntry": 3669,
        "BaseLine": 1,
        "ItemCode": "BatchItem_01",
        "Quantity": 1.0
      },
      {
        "LineNum": 1,
        "BaseType": 22,
        "BaseEntry": 3669,
        "BaseLine": 2,
        "ItemCode": "Non_sr_bt",
        "Quantity": 1.0
      },
      {
        "LineNum": 2,
        "BaseType": 22,
        "BaseEntry": 3670,
        "BaseLine": 0,
        "ItemCode": "BatchItem_01",
        "Quantity": 1.0
      }
    ]
  }
  ```

### 4. Batch/Serial Number Handling
- `BatchNumbers` array no longer includes `BaseLineNumber` (removed)
- `SerialNumbers` array no longer includes `BaseLineNumber` (removed)
- SAP B1 automatically associates batch/serial with the correct line based on document structure

## Sample JSON Output

```json
{
  "CardCode": "3D SPL",
  "Comments": "Auto-created from batch MGRN-20251114065000",
  "NumAtCard": "MGRN-20251114065000",
  "BPL_IDAssignedToInvoice": 5,
  "DocumentLines": [
    {
      "LineNum": 0,
      "ItemCode": "BatchItem_01",
      "Quantity": 1.0,
      "BaseType": 22,
      "BaseEntry": 3669,
      "BaseLine": 1,
      "WarehouseCode": "7000-FG",
      "DocumentLinesBinAllocations": [
        {
          "BinAbsEntry": 968,
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
    },
    {
      "LineNum": 1,
      "ItemCode": "Non_sr_bt",
      "Quantity": 1.0,
      "BaseType": 22,
      "BaseEntry": 3669,
      "BaseLine": 2,
      "WarehouseCode": "7000-FG",
      "DocumentLinesBinAllocations": [
        {
          "BinAbsEntry": 231,
          "Quantity": 10.0
        }
      ]
    },
    {
      "LineNum": 2,
      "BaseType": 22,
      "BaseEntry": 3670,
      "BaseLine": 0,
      "ItemCode": "BatchItem_01",
      "Quantity": 1.0,
      "WarehouseCode": "7000-FG",
      "DocumentLinesBinAllocations": [
        {
          "BinAbsEntry": 968,
          "Quantity": 10.0
        }
      ],
      "BatchNumbers": [
        {
          "BatchNumber": "483480042",
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

## Testing Checklist

- [ ] Select multiple POs with line items
- [ ] Verify bin locations are populated from UI (e.g., "7000-FG-A101")
- [ ] Verify BinAbsEntry is fetched from SAP BinLocations API
- [ ] Verify batch-managed items include BatchNumbers array
- [ ] Verify non-batch items do NOT include BatchNumbers
- [ ] Verify all lines have sequential LineNum (0, 1, 2, 3...)
- [ ] Verify each line maintains its own BaseEntry and BaseLine
- [ ] Post to SAP and verify single GRN is created
- [ ] Verify all PO links reference the same SAP GRN DocNum
- [ ] Test failure scenario - verify all POs remain unposted on error

## SAP B1 Compatibility

✅ **SAP Business One Service Layer supports consolidating multiple POs into a single Purchase Delivery Note** as long as:
- All POs are from the same vendor (CardCode)
- Currency and branch settings are consistent
- Tax rules align

The system validates these conditions by using the first PO's `CardCode` for the consolidated GRN.

## API Endpoints Used

### 1. Get BinAbsEntry
```
GET /b1s/v1/BinLocations?$filter=BinCode eq '7000-FG-A101'
Response: { "value": [{ "AbsEntry": 968, "Warehouse": "7000-FG", "BinCode": "7000-FG-A101" }] }
```

### 2. Create Purchase Delivery Note
```
POST /b1s/v1/PurchaseDeliveryNotes
Body: { consolidated GRN JSON }
Response: { "DocEntry": 1234, "DocNum": "5678" }
```

## Error Handling

**Atomic Operation:** The entire consolidated GRN posting is treated as atomic:
- **Success:** All PO links are marked as 'posted' with same GRN DocNum
- **Failure:** All PO links remain in 'selected' status, error is logged in batch

## Limitations & Future Enhancements

### Current Limitations

**1. Limited Header Field Validation:**
- The database currently doesn't store all PO header fields (Series, BPL, DocCurrency, Tax, Payment Terms)
- Validation is limited to CardCode (vendor) only
- Other field consistency is ensured through workflow design (series filtering in Step 1-2)

**2. Hard-Coded BPL:**
- `BPL_IDAssignedToInvoice` is hard-coded to 5 as per business requirement
- All POs should belong to the same branch (enforced by series selection)
- Cannot validate this at posting time with current schema

**3. Single NumAtCard:**
- Consolidated GRN uses batch number as NumAtCard
- Individual PO reference numbers are preserved in Comments field only
- This follows the user's sample JSON structure

### Future Enhancements

1. **Enhanced Database Schema:**
   ```sql
   -- Add to multi_grn_po_links table:
   ALTER TABLE multi_grn_po_links ADD COLUMN po_series INT;
   ALTER TABLE multi_grn_po_links ADD COLUMN po_bpl_id INT;
   ALTER TABLE multi_grn_po_links ADD COLUMN po_doc_currency VARCHAR(10);
   ```

2. **Comprehensive Header Validation:**
   - Validate Series, BPL, Currency match across all POs
   - Abort early with clear error messages identifying mismatched POs
   - Provide per-PO attribution in error messages

3. **Dynamic BPL Assignment:**
   - Use batch.series BPL metadata instead of hard-coding
   - Validate all POs match the expected BPL

## Related Files

- `modules/multi_grn_creation/routes.py` - `create_step5_post()` method (lines 335-545)
- `modules/multi_grn_creation/services.py` - `get_bin_abs_entry()` method (lines 466-518)
- `modules/multi_grn_creation/models.py` - Database models (no changes)

## Change Log

**2025-11-14:**
- ✅ Implemented consolidated single GRN JSON posting
- ✅ Added BinAbsEntry lookup from SAP BinLocations API
- ✅ Fixed DocumentLinesBinAllocations structure
- ✅ Implemented sequential LineNum across multiple POs
- ✅ Updated atomic batch status tracking
- ✅ Removed BaseLineNumber from batch/serial arrays (not needed)
- ✅ Added CardCode validation to prevent mixed-vendor batches
- ✅ Preserved per-PO metadata in Comments field
- ✅ Added validation to prevent empty GRN posting
- ✅ Documented limitations and future enhancements
