# Inventory Counting Modal Feature

**Date**: 2025-12-11  
**Feature**: Added popup modal for "New Count" in Inventory Counting History page

## Changes

### 1. Fixed strftime Error
- Added `safe_format_datetime()` helper function to handle both datetime objects and strings
- Applied to `LoadedAt` and `LastUpdatedAt` fields in `/api/get-local-invcnt-details`

### 2. Added "New Count" Popup Modal
Similar to the Inventory Transfer module, the Inventory Counting History page now has a popup modal for creating new counting documents instead of navigating to a separate page.

**Modal Features:**
- Document Series dropdown (loads from `/api/get-invcnt-series`)
- Document Number dropdown (loads from `/api/get-open-invcnt-docnums?series=X`)
- Scan button for barcode scanning
- Open Counting button to navigate to SAP Counting page with selected document

## UI Changes (templates/inventory_counting_history.html)

1. Changed "New Count" button from link to modal trigger
2. Added "newCountModal" modal with:
   - Series selection dropdown
   - Document number dropdown (cascading from series)
   - Hidden fields for doc_entry and series
   - Open Counting button

3. Added JavaScript functions:
   - `loadInvcntSeries()` - Loads series on modal open
   - `loadInvcntDocNumbers(series)` - Loads open documents for selected series
   - `onDocNumberSelected(select)` - Handles document selection
   - `openSelectedCount()` - Navigates to SAP Counting page
   - Modal reset on close

## Database Changes

No database schema changes required - this is a UI/code-only change.
