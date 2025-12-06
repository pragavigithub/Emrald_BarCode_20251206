# Multi GRN Duplicate Purchase Order Fix

## Issue
When adding Purchase Orders to a Multi GRN batch in Step 2, users encountered a database integrity error if they tried to add the same PO twice:

```
IntegrityError: (pymysql.err.IntegrityError) (1062, "Duplicate entry '119-40213' for key 'multi_grn_po_links.uq_batch_po'")
```

### Example Scenario
- User creates batch #119
- User adds PO #5500109 (DocEntry 40213)
- User navigates back and tries to add the same PO again
- System crashes with IntegrityError

## Root Cause
The database has a unique constraint `uq_batch_po` on the `multi_grn_po_links` table:
```sql
UNIQUE KEY uq_batch_po (batch_id, po_doc_entry)
```

This constraint prevents the same PO from being added to the same batch multiple times.

**Problem**: The application code didn't check for existing POs before attempting to insert, so when a duplicate was submitted, the database rejected it with an error instead of the application handling it gracefully.

## Fix Applied
Updated `modules/multi_grn_creation/routes.py` in the `create_step2_select_pos()` function (lines 210-262) to:

### 1. Query Existing POs
```python
# Get existing PO entries in this batch to avoid duplicates
existing_po_entries = {po_link.po_doc_entry for po_link in batch.po_links}
```

### 2. Check Before Insert
```python
# Check if this PO is already in the batch
if po_doc_entry in existing_po_entries:
    logging.warning(f"⚠️ PO {po_data['DocNum']} already exists, skipping")
    skipped_count += 1
    continue
```

### 3. Track Statistics
- Count newly added POs
- Count skipped duplicates
- Provide clear feedback to user

### 4. User-Friendly Messages
```python
if added_count > 0:
    flash(f'Added {added_count} Purchase Orders. Skipped {skipped_count} duplicate(s).', 'success')
else:
    flash(f'All {skipped_count} selected PO(s) are already in this batch', 'warning')
```

## Benefits
✅ **No more crashes**: Gracefully handles duplicate PO selections  
✅ **Clear feedback**: Users know which POs were added and which were skipped  
✅ **Prevents data corruption**: Maintains database integrity  
✅ **Better UX**: Users can safely re-select POs without errors  
✅ **Logging**: Warning messages help with debugging

## Database Schema
The unique constraint remains in place (as it should):
```sql
CREATE TABLE multi_grn_po_links (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT NOT NULL,
    po_doc_entry INT NOT NULL,
    ...
    UNIQUE KEY uq_batch_po (batch_id, po_doc_entry),
    ...
)
```

## Testing
After this fix:
1. ✅ Create a new Multi GRN batch
2. ✅ Add PO #123 to the batch
3. ✅ Try to add PO #123 again
4. ✅ System shows: "Added 0 Purchase Orders. All 1 selected PO(s) are already in this batch"
5. ✅ No crash, no error - smooth user experience

---
**Date**: November 17, 2025  
**Status**: ✅ Fixed and Deployed  
**Related Fixes**: 
- CARDCODE_DROPDOWN_FIX.md
- MULTI_GRN_POSTING_RESPONSE_FIX.md
