# Multi GRN Batch Details Label Linking Table

## Date: 2025-11-23

## Problem Statement

When entering **Number of Packs = 3** in the Multi GRN module's batch details, the system was only generating **1 QR label** showing "1 of 1" with quantity 3. The remaining 2 labels were missing, making it impossible to track individual packs.

### Before (Issue):
- User enters: Quantity = 7, Number of Packs = 3
- Database: Only 1 record in `multi_grn_batch_details`
- QR Labels Generated: Only 1 label (Pack 1 of 1, Qty: 3)
- **Missing**: Packs 2 and 3 were not tracked

## Solution Implemented

Created a new **linking table** `multi_grn_batch_details_label` to track each individual pack/QR label with its own unique GRN number.

### New Database Structure:

```
multi_grn_batch_details (parent)
    ├─ id: 1
    ├─ batch_number: "20251123-BatchItem_1"
    ├─ quantity: 7.000 (total)
    ├─ no_of_packs: 3
    └─ grn_number: "MGN-19-43-1"

multi_grn_batch_details_label (child - NEW TABLE)
    ├─ id: 1, batch_detail_id: 1, pack_number: 1, qty_in_pack: 3, grn_number: "MGN-19-43-1-1"
    ├─ id: 2, batch_detail_id: 1, pack_number: 2, qty_in_pack: 2, grn_number: "MGN-19-43-1-2"
    └─ id: 3, batch_detail_id: 1, pack_number: 3, qty_in_pack: 2, grn_number: "MGN-19-43-1-3"
```

### After (Fixed):
- User enters: Quantity = 7, Number of Packs = 3
- Database:
  - 1 record in `multi_grn_batch_details` (total quantity = 7, no_of_packs = 3)
  - 3 records in `multi_grn_batch_details_label` (one for each pack)
- QR Labels Generated: 3 unique labels
  - Label 1: Pack 1 of 3, Qty: 3, GRN: MGN-19-43-1-1
  - Label 2: Pack 2 of 3, Qty: 2, GRN: MGN-19-43-1-2
  - Label 3: Pack 3 of 3, Qty: 2, GRN: MGN-19-43-1-3

## Table Schema

```sql
CREATE TABLE multi_grn_batch_details_label (
    id                  SERIAL PRIMARY KEY,
    batch_detail_id     INTEGER NOT NULL REFERENCES multi_grn_batch_details(id) ON DELETE CASCADE,
    pack_number         INTEGER NOT NULL,
    qty_in_pack         NUMERIC(15,3) NOT NULL,
    grn_number          VARCHAR(50) NOT NULL UNIQUE,
    barcode             TEXT,
    qr_data             TEXT,
    printed             BOOLEAN DEFAULT FALSE,
    printed_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_batch_pack UNIQUE (batch_detail_id, pack_number)
);
```

## Key Features

1. **Unique GRN per Pack**: Each pack has its own unique GRN number (e.g., MGN-19-43-1-1, MGN-19-43-1-2)
2. **Quantity Distribution**: Automatically distributes total quantity across packs using integer division
3. **Print Tracking**: Tracks if each label has been printed and when
4. **QR Data Storage**: Stores the QR code data for each label
5. **Cascading Delete**: When batch_detail is deleted, all related labels are automatically deleted

## Code Changes

### 1. New Model (modules/multi_grn_creation/models.py)
- Added `MultiGRNBatchDetailsLabel` model
- Relationship: `batch_detail.pack_labels` to access all labels for a batch

### 2. Updated Routes (modules/multi_grn_creation/routes.py)
- **manage_batch_details()**: Creates 1 batch_detail + N label records (one per pack)
- **generate_qr_labels()**: Reads from label table to generate correct number of labels
- Each label now has proper pack number, quantity, and unique GRN

### 3. Migration Files
- **PostgreSQL**: Applied to development database ✓
- **MySQL**: `migrations/mysql_multi_grn_batch_details_label_table.sql`

## Benefits

1. ✅ **Accurate Label Count**: 3 packs = 3 labels (not just 1)
2. ✅ **Unique Tracking**: Each QR label has a unique GRN number
3. ✅ **Proper Quantity Distribution**: 7 units ÷ 3 packs = [3, 2, 2]
4. ✅ **Audit Trail**: Track which labels have been printed and when
5. ✅ **Database Integrity**: Foreign key constraints ensure data consistency

## Testing

To test the fix:
1. Go to Multi GRN → Create/Edit batch
2. Enter batch details with Number of Packs = 3
3. Click "Generate QR Labels"
4. Verify: 3 separate labels are generated, each with unique GRN and correct quantities

## Migration Instructions

### For PostgreSQL (Replit):
- Already applied to development database ✓

### For MySQL (Local):
```bash
mysql -u your_user -p your_database < migrations/mysql_multi_grn_batch_details_label_table.sql
```

Or via MySQL Workbench:
1. Open the migration file
2. Execute the SQL script
3. Verify the table was created successfully
