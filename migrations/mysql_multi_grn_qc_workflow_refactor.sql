-- MySQL Migration: Multi GRN Module - QC Approval Workflow Refactoring
-- Created: November 22, 2025
-- Purpose: Document the workflow refactoring where SAP posting is moved from Multi GRN screen to QC Dashboard

/*
BUSINESS REQUIREMENT:
---------------------
Multi GRN batches must go through QC approval before SAP posting.
Direct SAP posting from Multi GRN screen is removed.
All SAP B1 posting happens exclusively through the QC Dashboard.

WORKFLOW CHANGES:
-----------------
OLD WORKFLOW (Direct Posting):
  draft → completed (posted directly to SAP from Multi GRN screen)

NEW WORKFLOW (QC Approval Required):
  draft → submitted → qc_approved → posted
         ↓
      rejected (if QC rejects)

STATUS VALUES:
--------------
- draft:       Batch being created, items being selected
- submitted:   Batch submitted for QC approval (no SAP posting yet)
- qc_approved: QC has approved the batch (internal status transition)
- posted:      Consolidated GRN successfully posted to SAP B1
- rejected:    QC has rejected the batch
- failed:      SAP posting failed after QC approval

CONSOLIDATED POSTING LOGIC:
---------------------------
Multiple Purchase Orders → Single GRN Document

Example JSON Structure (from QC Dashboard approval):
{
    "CardCode": "3D SPL",
    "DocDate": "2025-11-19",
    "DocDueDate": "2025-11-19",
    "Comments": "QC Approved - Batch MGRN-20251119135318. POs: 252630035, 252630036",
    "NumAtCard": "MGRN-20251119135318",
    "BPL_IDAssignedToInvoice": 5,
    "DocumentLines": [
        {
            "LineNum": 0,
            "BaseType": 22,
            "BaseEntry": 3674,
            "BaseLine": 0,
            "ItemCode": "Non_Sr_Bt",
            "Quantity": 9.0,
            "WarehouseCode": "7000-FG",
            "DocumentLinesBinAllocations": [...]
        },
        {
            "LineNum": 1,
            "BaseType": 22,
            "BaseEntry": 3674,
            "BaseLine": 1,
            "ItemCode": "BatchItem_01",
            "Quantity": 9.0,
            "WarehouseCode": "7000-FG",
            "BatchNumbers": [...],
            "DocumentLinesBinAllocations": [...]
        },
        {
            "LineNum": 2,
            "BaseType": 22,
            "BaseEntry": 3675,
            "BaseLine": 0,
            ...
        }
    ]
}

KEY FEATURES:
-------------
1. Lines from multiple POs (BaseEntry: 3674, 3675) are consolidated
2. Sequential LineNum across all lines (0, 1, 2, 3, 4...)
3. Base references (BaseType, BaseEntry, BaseLine) link to source POs
4. All batch numbers, serial numbers, and bin allocations preserved

AFFECTED DATABASE TABLES:
--------------------------
- multi_grn_document: Status field now uses expanded workflow
- No schema changes required (tables already support the workflow)

EXISTING FIELDS (Already Support New Workflow):
------------------------------------------------
multi_grn_document:
  - status (VARCHAR(20)): Now uses: draft, submitted, qc_approved, posted, rejected, failed
  - submitted_at (DATETIME): Timestamp when batch submitted for QC
  - qc_approver_id (INT): Foreign key to users.id (QC approver)
  - qc_approved_at (DATETIME): Timestamp when QC approved
  - qc_notes (TEXT): QC approval/rejection notes
  - posted_at (DATETIME): Timestamp when posted to SAP B1

CODE CHANGES:
-------------
1. modules/multi_grn_creation/routes.py:
   - create_step5_post(): Changed from SAP posting to QC submission
   - approve_batch(): Added consolidated SAP posting logic
   
2. modules/multi_grn_creation/templates/multi_grn/step4_review.html:
   - Changed "Confirm & Post GRNs" → "Submit for QC Approval"
   - Updated success message to indicate QC approval required
   
3. templates/qc_dashboard.html:
   - Fixed route paths to /multi-grn/batch/{id}/approve and /reject
   - Updated approval message to mention consolidated GRN creation

4. modules/multi_grn_creation/models.py:
   - Added comprehensive status workflow documentation
   - Updated docstrings to reflect QC approval requirement

TESTING CHECKLIST:
------------------
[ ] Create Multi GRN batch (draft status)
[ ] Submit batch for QC approval (status → submitted)
[ ] Verify batch appears in QC Dashboard
[ ] QC approve batch (status → qc_approved → posted)
[ ] Verify consolidated GRN created in SAP B1
[ ] Verify all PO links have same GRN doc number
[ ] Test QC rejection workflow (status → rejected)

ROLLBACK NOTES:
---------------
If rollback is needed, the database schema remains unchanged.
Only application code changes need to be reverted.
All status transitions are backward compatible.
*/

-- NO SCHEMA CHANGES REQUIRED
-- This migration is documentation-only
-- The existing schema already supports the new workflow

-- Verify existing columns (informational query)
-- SHOW COLUMNS FROM multi_grn_document LIKE 'status';
-- SHOW COLUMNS FROM multi_grn_document LIKE 'submitted_at';
-- SHOW COLUMNS FROM multi_grn_document LIKE 'qc_approver_id';
-- SHOW COLUMNS FROM multi_grn_document LIKE 'qc_approved_at';
-- SHOW COLUMNS FROM multi_grn_document LIKE 'qc_notes';
-- SHOW COLUMNS FROM multi_grn_document LIKE 'posted_at';

-- Migration complete: Workflow refactoring documented
-- No database changes needed
