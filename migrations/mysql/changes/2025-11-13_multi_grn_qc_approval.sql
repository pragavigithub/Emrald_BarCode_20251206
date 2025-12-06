-- Multi GRN Batch QC Approval Fields Migration
-- Created: 2025-11-13
-- Description: Adds QC approval workflow fields to Multi GRN batch module

-- Add QC approval fields to multi_grn_batches table
ALTER TABLE multi_grn_batches 
ADD COLUMN qc_approver_id INT NULL AFTER user_id,
ADD COLUMN qc_approved_at DATETIME NULL AFTER qc_approver_id,
ADD COLUMN qc_notes TEXT NULL AFTER qc_approved_at,
ADD COLUMN submitted_at DATETIME NULL AFTER qc_notes,
ADD CONSTRAINT fk_multi_grn_batch_qc_approver FOREIGN KEY (qc_approver_id) REFERENCES users(id);

-- Update status column comment to reflect new statuses
ALTER TABLE multi_grn_batches
MODIFY COLUMN status VARCHAR(20) DEFAULT 'draft' COMMENT 'draft, submitted, qc_approved, posted, rejected, failed';

-- Add indexes for QC queries
CREATE INDEX idx_multi_grn_batch_status ON multi_grn_batches(status);
CREATE INDEX idx_multi_grn_batch_qc_approved_at ON multi_grn_batches(qc_approved_at);
CREATE INDEX idx_multi_grn_batch_submitted_at ON multi_grn_batches(submitted_at);
