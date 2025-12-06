# Multi GRN Module - QR Code Pack Tracking Guide
**Date:** November 23, 2025  
**Status:** ✅ Fully Implemented

## Overview
The Multi GRN module now fully supports QR code scanning with pack-level tracking. Each pack gets a unique GRN number that includes the pack index, allowing precise verification during QC approval.

---

## Database Schema Updates

### MySQL Migrations Updated
The following MySQL migration files have been updated to match the PostgreSQL schema:

1. **`migrations/mysql_multi_grn_consolidated.sql`** - Main consolidated schema
2. **`migrations/mysql_multi_grn_qc_verification_status.sql`** - New migration for status column

### Key Columns in `multi_grn_batch_details` Table

| Column | Type | Description |
|--------|------|-------------|
| `grn_number` | VARCHAR(50) | **Unique GRN number per pack** (e.g., `MGN-13-22-1-3` = batch 13, line 22, item 1, pack 3) |
| `quantity` | DECIMAL(15,3) | Quantity in THIS specific pack |
| `qty_per_pack` | DECIMAL(15,3) | Quantity per pack (same as quantity) |
| `no_of_packs` | INT | Always `1` (each record = 1 pack) |
| `status` | VARCHAR(20) | **`pending`** or **`verified`** (changed by QR scanning) |
| `batch_number` | VARCHAR(100) | Batch number (e.g., `20251123-BatchItem_-1`) |

### GRN Number Format
```
MGN-{batch_id}-{line_selection_id}-{batch_idx}-{pack_num}

Example: MGN-17-39-1-2
         │   │  │  │ └─ Pack 2 (of 3)
         │   │  │  └─── Batch item #1
         │   │  └────── Line selection #39
         │   └───────── Multi GRN batch #17
         └───────────── Multi GRN prefix
```

---

## How Pack Tracking Works

### Step 1: Create Multi GRN Batch
When a user creates a Multi GRN batch with multiple packs, the system:

1. Calculates total quantity and number of packs
2. Divides quantity evenly across packs
3. Creates **separate database records** for each pack
4. Assigns unique `grn_number` to each pack

#### Example:
```python
Item: BatchItem_002
Total Quantity: 6.000
Number of Packs: 3

Result in database:
┌────┬──────────┬─────────────────┬──────────┬──────────────┬──────────┬────────┐
│ id │ batch_   │ grn_number      │ quantity │ qty_per_pack │ no_of_   │ status │
│    │ number   │                 │          │              │ packs    │        │
├────┼──────────┼─────────────────┼──────────┼──────────────┼──────────┼────────┤
│ 45 │ 20251123 │ MGN-13-22-1-1   │ 2.000    │ 2.000        │ 1        │ pending│
│ 46 │ 20251123 │ MGN-13-22-1-2   │ 2.000    │ 2.000        │ 1        │ pending│
│ 47 │ 20251123 │ MGN-13-22-1-3   │ 2.000    │ 2.000        │ 1        │ pending│
└────┴──────────┴─────────────────┴──────────┴──────────────┴──────────┴────────┘
```

### Step 2: Generate QR Labels
The system generates individual QR code labels for each pack:

```json
QR Code Data (JSON format):
{
  "id": "MGN-13-22-1-1",
  "po": "2526530044",
  "item": "BatchItem_002",
  "batch": "20251123-BatchItem_-1",
  "qty": 2,
  "pack": "1 of 3",
  "grn_date": "2025-11-23",
  "exp_date": "2025-12-06"
}
```

Each QR label displays:
- **Full GRN number** (e.g., `MGN-17-39-1-2`)
- **Pack information** (e.g., "Pack: 2 of 3")
- **Quantity in this pack** (e.g., "Qty per Pack: 2")
- Batch number, PO number, item code, expiry date

### Step 3: QC Dashboard - Scan QR Codes
QC personnel scan each QR label using the QC Review page:

1. **Open QC Review page** for the batch
2. **Scan QR code** using camera or manual entry
3. **System validates**:
   - ✅ GRN number exists in database
   - ✅ Scanned quantity matches database quantity
   - ✅ Item hasn't already been verified
4. **Mark as verified** - Status changes from `pending` to `verified`

#### API Endpoint: `/api/scan-qr-code`
```python
# Decodes QR JSON data
qr_json = json.loads(qr_data)
grn_id = qr_json.get('id')      # e.g., "MGN-13-22-1-2"
qr_qty = qr_json.get('qty')     # e.g., 2

# Query database using FULL GRN number (includes pack number)
batch_detail = MultiGRNBatchDetails.query.filter_by(grn_number=grn_id).first()

# Validate quantity matches
db_pack_qty = int(float(batch_detail.quantity))
qr_pack_qty = int(qr_qty)

if qr_pack_qty != db_pack_qty:
    return error("Quantity mismatch!")

# Mark as verified
batch_detail.status = 'verified'
db.session.commit()
```

### Step 4: QC Approval Enforcement
The system **prevents QC approval** until ALL packs are verified:

```python
# Count total items and verified items
for line in batch.po_links.line_selections:
    batch_details = MultiGRNBatchDetails.query.filter_by(line_selection_id=line.id).all()
    
    for detail in batch_details:
        total_items += 1
        if detail.status == 'verified':
            verified_items += 1

# Block approval if not all verified
if verified_items != total_items:
    return error(f'Not all items verified. {verified_items}/{total_items} items verified.')
```

---

## Key Features

### ✅ Pack-Level GRN Numbers
- Each pack has a **unique GRN number** with pack suffix
- Database filter uses **full GRN number** (including pack number)
- No ambiguity - each QR code maps to exactly one database record

### ✅ Quantity Verification
- QR code contains expected quantity
- System compares QR qty vs database qty
- **Rejects mismatches** - prevents errors

### ✅ Status Tracking
- **`pending`** - Not yet scanned
- **`verified`** - Scanned and validated

### ✅ QC Enforcement
- Cannot approve until **all items verified**
- Real-time verification progress display
- Clear error messages for missing scans

---

## Code Locations

### Models
- **`modules/multi_grn_creation/models.py`** - Lines 125-140 (MultiGRNBatchDetails)
- **`modules/multi_grn_creation/models.py`** - Lines 147-160 (MultiGRNSerialDetails)

### Routes
- **`modules/multi_grn_creation/routes.py`**
  - Line 962-1087: `scan_qr_code()` - QR scanning endpoint
  - Line 655-674: QC approval verification
  - Line 2300-2385: Batch detail creation with pack distribution

### Templates
- **`modules/multi_grn_creation/templates/multi_grn/qc_review.html`** - QC scanning interface

---

## Migration Files

### PostgreSQL (Replit Environment)
Automatic - handled by SQLAlchemy models in `app.py`:
```python
db.create_all()  # Creates tables with all columns including 'status'
```

### MySQL (Local/Production)
Run these migration files in order:

1. **`migrations/mysql_multi_grn_consolidated.sql`**
   - Creates all Multi GRN tables
   - Includes `status` column in batch/serial details

2. **`migrations/mysql_multi_grn_qc_verification_status.sql`**
   - Adds `status` column if missing (for existing databases)
   - Updates NULL values to 'pending'

To apply:
```sql
SOURCE migrations/mysql_multi_grn_consolidated.sql;
SOURCE migrations/mysql_multi_grn_qc_verification_status.sql;
```

---

## Troubleshooting

### Issue: GRN Number is NULL
**Cause:** Batch was created before pack-tracking was implemented  
**Solution:** 
1. Delete and recreate the batch
2. Or manually update `grn_number` using pattern: `MGN-{batch_id}-{line_id}-{item_idx}-{pack_num}`

### Issue: Can't Find Pack When Scanning
**Cause:** QR code GRN doesn't match database GRN  
**Solution:**
1. Verify QR code format is correct JSON
2. Check database for exact `grn_number` match
3. Ensure pack number suffix is included

### Issue: Quantity Mismatch Error
**Cause:** QR label quantity doesn't match database  
**Solution:**
1. Regenerate QR labels from Step 3
2. Ensure pack distribution is correct
3. Check if quantity was manually edited

---

## Example Workflow

### Complete Example: 3-Pack Batch

```
1. Create Batch
   - Item: BatchItem_002
   - Total Qty: 6
   - Packs: 3
   
2. Database Records Created:
   ┌─────────────────┬──────────┬────────────┐
   │ grn_number      │ quantity │ status     │
   ├─────────────────┼──────────┼────────────┤
   │ MGN-17-39-1-1   │ 2.000    │ pending    │
   │ MGN-17-39-1-2   │ 2.000    │ pending    │
   │ MGN-17-39-1-3   │ 2.000    │ pending    │
   └─────────────────┴──────────┴────────────┘

3. Generate QR Labels (Step 3)
   - 3 labels created, each with unique GRN

4. QC Scans Labels
   Scan 1: MGN-17-39-1-1 → ✅ Verified
   Scan 2: MGN-17-39-1-2 → ✅ Verified
   Scan 3: MGN-17-39-1-3 → ✅ Verified

5. Approve Batch
   - All 3/3 items verified ✅
   - QC approval allowed
   - Post to SAP B1
```

---

## Summary

✅ **MySQL migrations updated** with `status` column  
✅ **Pack information (`no_of_packs`) saved** in database  
✅ **GRN numbers include pack suffix** for unique identification  
✅ **QR scanning filters by full GRN number** (including pack)  
✅ **Quantity verification enforced** before marking verified  
✅ **QC approval blocked** until all items verified  

The system is fully functional and ready for production use!
