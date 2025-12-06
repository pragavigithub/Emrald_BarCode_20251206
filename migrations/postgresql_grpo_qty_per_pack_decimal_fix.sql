-- Migration to support decimal quantities in GRPO QR label generation
-- Changes qty_per_pack from INTEGER to DECIMAL(15,3) in grpo_non_managed_items table
-- Also updates quantity column to support decimal values
-- Date: 2025-11-12
-- Related to: QR Label Decimal Quantity Distribution Fix
-- Database: PostgreSQL

-- Modify qty_per_pack to support decimal values (3 decimal places)
ALTER TABLE grpo_non_managed_items 
ALTER COLUMN qty_per_pack TYPE DECIMAL(15, 3);

-- Also update quantity column to support decimal values for consistency
ALTER TABLE grpo_non_managed_items 
ALTER COLUMN quantity TYPE DECIMAL(15, 3);

-- Verify the changes
SELECT 
    column_name, 
    data_type, 
    numeric_precision,
    numeric_scale,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'grpo_non_managed_items' 
  AND column_name IN ('qty_per_pack', 'quantity')
ORDER BY column_name;
