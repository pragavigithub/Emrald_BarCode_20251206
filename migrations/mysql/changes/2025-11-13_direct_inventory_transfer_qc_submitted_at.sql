-- Direct Inventory Transfer submitted_at Field Migration
-- Created: 2025-11-13
-- Description: Adds submitted_at field to Direct Inventory Transfer module for QC workflow

-- Add submitted_at field to direct_inventory_transfers table
ALTER TABLE direct_inventory_transfers 
ADD COLUMN submitted_at DATETIME NULL AFTER qc_notes;

-- Add index for submitted_at queries
CREATE INDEX idx_direct_inventory_transfer_submitted_at ON direct_inventory_transfers(submitted_at);
