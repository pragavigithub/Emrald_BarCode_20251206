-- MySQL Migration: Add multi_grn_batch_details_label table
-- Purpose: Track individual pack labels for batch items with unique GRN numbers
-- Created: 2025-11-23
-- 
-- This table solves the issue where entering 3 packs only generated 1 QR label.
-- Now each pack gets its own unique record with a unique GRN number for tracking.
--
-- Example: If batch_details has quantity=7 and no_of_packs=3:
--   - Label 1: pack_number=1, qty_in_pack=3, grn_number=MGN-19-43-1-1
--   - Label 2: pack_number=2, qty_in_pack=2, grn_number=MGN-19-43-1-2
--   - Label 3: pack_number=3, qty_in_pack=2, grn_number=MGN-19-43-1-3

-- Create the new linking table
CREATE TABLE IF NOT EXISTS multi_grn_batch_details_label (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_detail_id INT NOT NULL,
    pack_number INT NOT NULL,
    qty_in_pack DECIMAL(15,3) NOT NULL,
    grn_number VARCHAR(50) NOT NULL UNIQUE,
    barcode TEXT,
    qr_data TEXT,
    printed TINYINT(1) DEFAULT 0,
    printed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to multi_grn_batch_details
    CONSTRAINT fk_batch_detail 
        FOREIGN KEY (batch_detail_id) 
        REFERENCES multi_grn_batch_details(id) 
        ON DELETE CASCADE,
    
    -- Unique constraint to ensure one record per pack per batch_detail
    CONSTRAINT uq_batch_pack 
        UNIQUE KEY (batch_detail_id, pack_number),
    
    -- Index for faster lookups
    INDEX idx_grn_number (grn_number),
    INDEX idx_batch_detail_id (batch_detail_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add comment to the table
ALTER TABLE multi_grn_batch_details_label 
COMMENT = 'Individual pack labels for Multi GRN batch items - each record represents one physical QR label with unique GRN';
