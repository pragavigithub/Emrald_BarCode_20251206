-- Migration: Inventory Counting Local Storage Enhancement
-- Date: 2025-12-11
-- Description: Fixed bug where inventory counting line items were not being stored locally
--              after submitting to SAP B1. This ensures history view shows all count line items.
-- Type: Code fix (no schema changes required)

-- ============================================================================
-- PROBLEM DESCRIPTION
-- ============================================================================
-- When users created/modified inventory counting documents and submitted them to SAP B1:
-- 1. Line items were not stored in the local MySQL database
-- 2. History view showed documents but with empty or missing line items
-- 3. Users could not see what items were counted after the document was closed in SAP

-- ROOT CAUSE:
-- Key name mismatch in the update_inventory_counting API endpoint:
-- - Frontend sends: 'InventoryCountingLines' (with 'ing' in Counting)
-- - Backend was looking for: 'InventoryCountLines' (missing 'ing')
-- This caused the line update loop to never execute.

-- ============================================================================
-- FIX APPLIED
-- ============================================================================
-- File: routes.py - update_inventory_counting() function

-- 1. Fixed key name to check both 'InventoryCountingLines' and 'InventoryCountLines'
--    for backward compatibility:
--    lines = document.get('InventoryCountingLines', []) or document.get('InventoryCountLines', [])

-- 2. Enhanced to create new line items if they don't exist locally
--    (previously only updated existing lines)

-- 3. Added logic to create new local document records if they don't exist
--    (handles documents created directly in SAP B1)

-- 4. When updating existing lines, now refreshes ALL relevant fields:
--    - item_code, item_description, warehouse_code
--    - in_warehouse_quantity, uom_counted_quantity
--    - counted status (tYES/tNO)
--    - variance calculation
--    - bin_entry, uom_code, bar_code
--    - items_per_unit, counter_type, counter_id, line_status
--    - Additional fields: u_floor, u_rack, u_level
--    (Previously only updated counted qty, counted flag, and variance)

-- 5. Added safe_float() helper function to handle None/blank values from SAP:
--    - Prevents TypeError when SAP returns null for numeric fields
--    - Provides default values (0 for quantities, 1 for items_per_unit)
--    - All numeric field assignments now use safe_float() for robustness

-- 6. Variance calculation improvement:
--    - When SAP omits the Variance field, it is now calculated as:
--      variance = uom_counted_quantity - in_warehouse_quantity
--    - This ensures variance data is always numerically correct in history

-- ============================================================================
-- EXISTING TABLE STRUCTURES (No schema changes)
-- ============================================================================
-- Table: sap_inventory_counts - Stores document headers
-- Table: sap_inventory_count_lines - Stores line items

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check documents with line items stored:
-- SELECT c.doc_entry, c.doc_number, c.document_status, 
--        COUNT(l.id) as line_count,
--        c.loaded_at, c.last_updated_at
-- FROM sap_inventory_counts c
-- LEFT JOIN sap_inventory_count_lines l ON c.id = l.count_id
-- GROUP BY c.id
-- ORDER BY c.last_updated_at DESC;

-- View line items for a specific document:
-- SELECT l.line_number, l.item_code, l.item_description,
--        l.in_warehouse_quantity, l.uom_counted_quantity, l.variance, l.counted
-- FROM sap_inventory_count_lines l
-- JOIN sap_inventory_counts c ON l.count_id = c.id
-- WHERE c.doc_entry = <YOUR_DOC_ENTRY>
-- ORDER BY l.line_number;

-- ============================================================================
-- WORKFLOW
-- ============================================================================
-- 1. User loads counting document from SAP -> Lines stored in local DB
-- 2. User modifies counted quantities and submits to SAP B1
-- 3. On successful update, local DB is updated with:
--    - Updated counted quantities and status
--    - Variance recalculated
--    - New lines created if they didn't exist locally
--    - New document created if it didn't exist locally
-- 4. History view can now display all line items from local database
