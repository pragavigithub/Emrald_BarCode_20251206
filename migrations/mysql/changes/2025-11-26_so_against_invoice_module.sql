-- ============================================================================
-- SO Against Invoice Module - MySQL Migration
-- ============================================================================
-- Date: 2025-11-26
-- Description: Creates tables for the SO Against Invoice module
-- This module allows creating invoices against existing Sales Orders
-- ============================================================================

-- SO Invoice Documents table (Header)
CREATE TABLE IF NOT EXISTS so_invoice_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_number VARCHAR(50) NOT NULL UNIQUE,
    sap_invoice_number VARCHAR(50),
    so_series INT,
    so_series_name VARCHAR(100),
    so_number VARCHAR(50),
    so_doc_entry INT,
    
    -- Customer details from SO
    card_code VARCHAR(50),
    card_name VARCHAR(200),
    customer_address TEXT,
    
    -- Invoice details
    doc_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    doc_due_date TIMESTAMP NULL,
    bplid INT,
    userSign INT,
    
    status VARCHAR(20) DEFAULT 'draft',
    user_id INT NOT NULL,
    
    -- Comments and tracking
    comments TEXT,
    validation_notes TEXT,
    posting_error TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_document_number (document_number),
    INDEX idx_so_number (so_number),
    INDEX idx_card_code (card_code),
    INDEX idx_status (status),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SO Invoice Items table (Line Items)
CREATE TABLE IF NOT EXISTS so_invoice_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    so_invoice_id INT NOT NULL,
    line_num INT NOT NULL,
    
    -- Item details from SO
    item_code VARCHAR(50) NOT NULL,
    item_description VARCHAR(200) NOT NULL,
    so_quantity DECIMAL(18, 6) NOT NULL,
    warehouse_code VARCHAR(10) NOT NULL,
    
    -- Validated item details
    validated_quantity DECIMAL(18, 6) DEFAULT 0,
    is_serial_managed BOOLEAN DEFAULT FALSE,
    is_batch_managed BOOLEAN DEFAULT FALSE,
    
    validation_status VARCHAR(20) DEFAULT 'pending',
    validation_error TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (so_invoice_id) REFERENCES so_invoice_documents(id) ON DELETE CASCADE,
    INDEX idx_so_invoice_id (so_invoice_id),
    INDEX idx_item_code (item_code),
    INDEX idx_validation_status (validation_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SO Invoice Serials table (Serial Numbers for Items)
CREATE TABLE IF NOT EXISTS so_invoice_serials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    so_invoice_item_id INT NOT NULL,
    serial_number VARCHAR(100) NOT NULL,
    quantity INT DEFAULT 1,
    base_line_number INT NOT NULL,
    
    validation_status VARCHAR(20) DEFAULT 'pending',
    validation_error TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (so_invoice_item_id) REFERENCES so_invoice_items(id) ON DELETE CASCADE,
    UNIQUE KEY unique_serial_per_invoice_item (so_invoice_item_id, serial_number),
    INDEX idx_so_invoice_item_id (so_invoice_item_id),
    INDEX idx_serial_number (serial_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SO Series Cache table (for faster lookup)
CREATE TABLE IF NOT EXISTS so_series_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    series INT NOT NULL UNIQUE,
    series_name VARCHAR(100) NOT NULL,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_series (series)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- Ensure document_number_series has SO_AGAINST_INVOICE entry
-- ============================================================================
INSERT INTO document_number_series (series_type, prefix, current_number, description)
SELECT 'SO_AGAINST_INVOICE', 'DOC-', 0, 'SO Against Invoice Documents'
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM document_number_series WHERE series_type = 'SO_AGAINST_INVOICE'
);

-- ============================================================================
-- End of Migration
-- ============================================================================
