-- Migration: Item Tracking Module
-- Date: 2025-12-10
-- Description: Add item_tracking permission to user permissions
-- This module uses SAP B1 SQL Query 'item_tracking' for fetching serial number tracking data

-- Note: The item_tracking module does not require any new database tables.
-- It fetches data directly from SAP B1 using the SQL Query:
-- URL: https://<SAP_SERVER>/b1s/v1/SQLQueries('item_tracking')/List
-- Method: POST
-- Body: {"ParamList": "serialNumber='<serial>'"}

-- SAP B1 DocType Mapping used in Item Tracking:
-- 2 = Journal Entry
-- 13 = A/R Invoice
-- 14 = A/R Credit Memo
-- 15 = Delivery
-- 16 = Return
-- 17 = Order
-- 18 = A/P Invoice
-- 19 = A/P Credit Memo
-- 20 = Goods Receipt PO
-- 21 = Goods Return
-- 22 = A/R Down Payment Invoice
-- 59 = Goods Receipt
-- 60 = Goods Issue
-- 67 = Inventory Transfer
-- 69 = Inventory Transfer Request
-- 162 = Inventory Counting
-- 202 = Production Order
-- 234 = Inventory Posting
-- 1250000001 = Inventory Opening Balance

-- Update user permissions to include item_tracking for existing users
-- This updates the JSON permissions field to add item_tracking: true for admin/manager/user roles

-- For MySQL: Update existing users with item_tracking permission
UPDATE users 
SET permissions = JSON_SET(
    COALESCE(permissions, '{}'), 
    '$.item_tracking', 
    CASE 
        WHEN role IN ('admin', 'manager', 'user') THEN TRUE
        ELSE FALSE
    END
)
WHERE permissions IS NOT NULL 
  AND JSON_VALID(permissions);

-- For users with NULL permissions, they will get default permissions from the code
-- when they log in next time (get_default_permissions() in models.py)
