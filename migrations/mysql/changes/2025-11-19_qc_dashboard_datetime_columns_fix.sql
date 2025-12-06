-- QC Dashboard DateTime Columns Type Fix
-- Created: 2025-11-19
-- Description: Ensures all datetime columns in QC-related tables are properly defined as DATETIME type
--              This fixes the Jinja2 template error where datetime fields were being returned as strings
--              instead of datetime objects, causing "str object has no attribute 'strftime'" errors

-- Fix Multi GRN Batches datetime columns
-- Ensure submitted_at, qc_approved_at, created_at, posted_at, completed_at are DATETIME type
ALTER TABLE multi_grn_batches 
MODIFY COLUMN submitted_at DATETIME NULL COMMENT 'When batch was submitted for QC approval',
MODIFY COLUMN qc_approved_at DATETIME NULL COMMENT 'When batch was approved/rejected by QC',
MODIFY COLUMN created_at DATETIME NOT NULL COMMENT 'When batch was created',
MODIFY COLUMN posted_at DATETIME NULL COMMENT 'When batch was posted to SAP',
MODIFY COLUMN completed_at DATETIME NULL COMMENT 'When batch processing completed';

-- Fix Direct Inventory Transfer datetime columns
-- Ensure submitted_at, qc_approved_at, created_at, updated_at are DATETIME type
ALTER TABLE direct_inventory_transfers
MODIFY COLUMN submitted_at DATETIME NULL COMMENT 'When transfer was submitted for QC approval',
MODIFY COLUMN qc_approved_at DATETIME NULL COMMENT 'When transfer was approved/rejected by QC',
MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When transfer was created',
MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When transfer was last updated';

-- Fix Sales Delivery datetime columns
-- Ensure submitted_at, qc_approved_at, created_at, updated_at are DATETIME type
ALTER TABLE sales_deliveries
MODIFY COLUMN submitted_at DATETIME NULL COMMENT 'When delivery was submitted for QC approval',
MODIFY COLUMN qc_approved_at DATETIME NULL COMMENT 'When delivery was approved/rejected by QC',
MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When delivery was created',
MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When delivery was last updated';

-- Fix GRPO datetime columns
-- Ensure created_at, updated_at, grn_date are DATETIME type
ALTER TABLE grpo_master
MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When GRPO was created',
MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When GRPO was last updated',
MODIFY COLUMN grn_date DATETIME NULL COMMENT 'GRN date from SAP';

-- Fix Inventory Transfer datetime columns
-- Ensure created_at, updated_at are DATETIME type
ALTER TABLE inventory_transfer_master
MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When transfer was created',
MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When transfer was last updated';

-- Verify the changes
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME IN (
    'multi_grn_batches',
    'direct_inventory_transfers',
    'sales_deliveries',
    'grpo_master',
    'inventory_transfer_master'
)
AND COLUMN_NAME LIKE '%_at' OR COLUMN_NAME LIKE '%_date'
ORDER BY TABLE_NAME, COLUMN_NAME;

-- Migration Notes:
-- 1. All datetime columns are now explicitly set to DATETIME type
-- 2. This ensures Python SQLAlchemy returns datetime objects instead of strings
-- 3. The qc_dashboard.html template has been updated with a safe macro to handle both datetime objects and strings
-- 4. Default values and ON UPDATE CURRENT_TIMESTAMP have been preserved where applicable
-- 5. Column comments added for better documentation
