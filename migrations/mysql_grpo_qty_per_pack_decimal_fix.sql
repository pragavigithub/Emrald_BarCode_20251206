-- Migration to support decimal quantities in GRPO QR label generation
-- Changes qty_per_pack from INTEGER to DECIMAL(15,3) in grpo_non_managed_items table
-- Also updates quantity column to support decimal values
-- Date: 2025-11-12
-- Related to: QR Label Decimal Quantity Distribution Fix

-- Modify qty_per_pack to support decimal values (3 decimal places)
ALTER TABLE grpo_non_managed_items 
MODIFY COLUMN qty_per_pack DECIMAL(15, 3);

-- Also update quantity column to support decimal values for consistency
ALTER TABLE grpo_non_managed_items 
MODIFY COLUMN quantity DECIMAL(15, 3) NOT NULL;

-- Verify the changes
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    COLUMN_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'grpo_non_managed_items' 
  AND COLUMN_NAME IN ('qty_per_pack', 'quantity')
ORDER BY COLUMN_NAME;
