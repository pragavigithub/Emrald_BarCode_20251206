-- ================================================================
-- Migration: Multi GRN QC Verification Status Column
-- Date: 2025-11-23
-- Description: Add status column to batch and serial details tables
--              for QC verification tracking. Ensures QR code scanning
--              can mark items as 'verified' before QC approval.
-- ================================================================

-- Add status column to multi_grn_batch_details if it doesn't exist
ALTER TABLE `multi_grn_batch_details` 
    ADD COLUMN IF NOT EXISTS `status` VARCHAR(20) DEFAULT 'pending' NOT NULL AFTER `no_of_packs`;

-- Add status column to multi_grn_serial_details if it doesn't exist
ALTER TABLE `multi_grn_serial_details` 
    ADD COLUMN IF NOT EXISTS `status` VARCHAR(20) DEFAULT 'pending' NOT NULL AFTER `no_of_packs`;

-- Add index for faster status filtering
ALTER TABLE `multi_grn_batch_details` 
    ADD INDEX IF NOT EXISTS `idx_batch_status` (`status`);

ALTER TABLE `multi_grn_serial_details` 
    ADD INDEX IF NOT EXISTS `idx_serial_status` (`status`);

-- ================================================================
-- Verification Queries (Run after migration to verify)
-- ================================================================

-- Verify status column was added to multi_grn_batch_details
-- SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT, IS_NULLABLE 
-- FROM information_schema.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() 
-- AND TABLE_NAME = 'multi_grn_batch_details' 
-- AND COLUMN_NAME = 'status';

-- Verify status column was added to multi_grn_serial_details
-- SELECT COLUMN_NAME, DATA_TYPE, COLUMN_DEFAULT, IS_NULLABLE 
-- FROM information_schema.COLUMNS 
-- WHERE TABLE_SCHEMA = DATABASE() 
-- AND TABLE_NAME = 'multi_grn_serial_details' 
-- AND COLUMN_NAME = 'status';

-- Check current status values
-- SELECT status, COUNT(*) as count 
-- FROM multi_grn_batch_details 
-- GROUP BY status;

-- ================================================================
-- Update existing records to 'pending' status if they have NULL
-- ================================================================
UPDATE `multi_grn_batch_details` 
SET `status` = 'pending' 
WHERE `status` IS NULL;

UPDATE `multi_grn_serial_details` 
SET `status` = 'pending' 
WHERE `status` IS NULL;

-- ================================================================
-- Notes
-- ================================================================
-- Status values used in the system:
--   'pending'  - Item created but not yet verified via QR scan
--   'verified' - Item scanned and quantity validated via QR code
-- 
-- QC Approval Process:
-- 1. User creates Multi GRN batch with line items and batch/serial details
-- 2. System generates QR labels with GRN numbers (including pack number)
-- 3. QC scans each QR label on the QC Review page
-- 4. System validates scanned quantity matches database quantity
-- 5. Upon successful validation, status changes from 'pending' to 'verified'
-- 6. QC can only approve the batch when ALL items are 'verified'
-- ================================================================

-- Rollback Instructions (if needed)
-- ALTER TABLE `multi_grn_batch_details` DROP COLUMN IF EXISTS `status`;
-- ALTER TABLE `multi_grn_serial_details` DROP COLUMN IF EXISTS `status`;
