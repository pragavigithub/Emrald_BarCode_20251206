#!/usr/bin/env python3
"""
MySQL Migration: Inventory Transfer SAP B1 Persistent Storage
Date: November 27, 2025

This migration adds SAP B1 Transfer Request storage fields to the Inventory Transfer module.
It stores SAP data exactly as received for later posting back to SAP B1.

Changes:
1. inventory_transfers table - Add SAP header fields
2. inventory_transfer_items table - Add SAP line fields  
3. inventory_transfer_request_lines table - NEW table for SAP StockTransferLines

Run: python migrations/mysql_inventory_transfer_sap_storage.py
"""

import os
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    logger.warning("PyMySQL not installed. Install with: pip install pymysql")

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError, ProgrammingError
except ImportError:
    logger.error("SQLAlchemy not installed. Install with: pip install sqlalchemy")
    sys.exit(1)


MIGRATION_NAME = "inventory_transfer_sap_storage"
MIGRATION_DATE = "2025-11-27"


ALTER_INVENTORY_TRANSFERS = """
-- Add SAP B1 Transfer Request Header Fields to inventory_transfers table
ALTER TABLE inventory_transfers
    ADD COLUMN IF NOT EXISTS sap_doc_entry INT NULL COMMENT 'SAP DocEntry identifier',
    ADD COLUMN IF NOT EXISTS sap_doc_num INT NULL COMMENT 'SAP document number',
    ADD COLUMN IF NOT EXISTS bpl_id INT NULL COMMENT 'Business Place ID',
    ADD COLUMN IF NOT EXISTS bpl_name VARCHAR(100) NULL COMMENT 'Business Place name',
    ADD COLUMN IF NOT EXISTS sap_document_status VARCHAR(20) NULL COMMENT 'Document status (bost_Open/bost_Close)',
    ADD COLUMN IF NOT EXISTS doc_date DATETIME NULL COMMENT 'Document date from SAP',
    ADD COLUMN IF NOT EXISTS due_date DATETIME NULL COMMENT 'Due date from SAP',
    ADD COLUMN IF NOT EXISTS sap_raw_json LONGTEXT NULL COMMENT 'Complete SAP response JSON';
"""

ALTER_INVENTORY_TRANSFERS_INDIVIDUAL = [
    ("sap_doc_entry", "ALTER TABLE inventory_transfers ADD COLUMN sap_doc_entry INT NULL COMMENT 'SAP DocEntry identifier'"),
    ("sap_doc_num", "ALTER TABLE inventory_transfers ADD COLUMN sap_doc_num INT NULL COMMENT 'SAP document number'"),
    ("bpl_id", "ALTER TABLE inventory_transfers ADD COLUMN bpl_id INT NULL COMMENT 'Business Place ID'"),
    ("bpl_name", "ALTER TABLE inventory_transfers ADD COLUMN bpl_name VARCHAR(100) NULL COMMENT 'Business Place name'"),
    ("sap_document_status", "ALTER TABLE inventory_transfers ADD COLUMN sap_document_status VARCHAR(20) NULL COMMENT 'Document status (bost_Open/bost_Close)'"),
    ("doc_date", "ALTER TABLE inventory_transfers ADD COLUMN doc_date DATETIME NULL COMMENT 'Document date from SAP'"),
    ("due_date", "ALTER TABLE inventory_transfers ADD COLUMN due_date DATETIME NULL COMMENT 'Due date from SAP'"),
    ("sap_raw_json", "ALTER TABLE inventory_transfers ADD COLUMN sap_raw_json LONGTEXT NULL COMMENT 'Complete SAP response JSON'"),
]

ADD_INDEX_SAP_DOC_ENTRY = """
CREATE INDEX IF NOT EXISTS idx_sap_doc_entry ON inventory_transfers(sap_doc_entry);
"""

ALTER_INVENTORY_TRANSFER_ITEMS = """
-- Add SAP B1 Line Fields to inventory_transfer_items table
ALTER TABLE inventory_transfer_items
    ADD COLUMN IF NOT EXISTS from_warehouse_code VARCHAR(20) NULL COMMENT 'Source warehouse code',
    ADD COLUMN IF NOT EXISTS to_warehouse_code VARCHAR(20) NULL COMMENT 'Destination warehouse code',
    ADD COLUMN IF NOT EXISTS sap_line_num INT NULL COMMENT 'SAP line number',
    ADD COLUMN IF NOT EXISTS sap_doc_entry INT NULL COMMENT 'SAP document entry',
    ADD COLUMN IF NOT EXISTS line_status VARCHAR(20) NULL COMMENT 'Line status (bost_Open/bost_Close)';
"""

ALTER_INVENTORY_TRANSFER_ITEMS_INDIVIDUAL = [
    ("from_warehouse_code", "ALTER TABLE inventory_transfer_items ADD COLUMN from_warehouse_code VARCHAR(20) NULL COMMENT 'Source warehouse code'"),
    ("to_warehouse_code", "ALTER TABLE inventory_transfer_items ADD COLUMN to_warehouse_code VARCHAR(20) NULL COMMENT 'Destination warehouse code'"),
    ("sap_line_num", "ALTER TABLE inventory_transfer_items ADD COLUMN sap_line_num INT NULL COMMENT 'SAP line number'"),
    ("sap_doc_entry", "ALTER TABLE inventory_transfer_items ADD COLUMN sap_doc_entry INT NULL COMMENT 'SAP document entry'"),
    ("line_status", "ALTER TABLE inventory_transfer_items ADD COLUMN line_status VARCHAR(20) NULL COMMENT 'Line status (bost_Open/bost_Close)'"),
]

CREATE_INVENTORY_TRANSFER_REQUEST_LINES = """
-- Create inventory_transfer_request_lines table to store SAP StockTransferLines exactly as received
CREATE TABLE IF NOT EXISTS inventory_transfer_request_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    inventory_transfer_id INT NOT NULL,
    -- SAP B1 StockTransferLines fields (stored exactly as received)
    line_num INT NOT NULL COMMENT 'SAP LineNum',
    sap_doc_entry INT NOT NULL COMMENT 'SAP DocEntry',
    item_code VARCHAR(50) NOT NULL COMMENT 'Item code',
    item_description VARCHAR(200) NULL COMMENT 'Item description',
    quantity DECIMAL(15,4) NOT NULL COMMENT 'Requested quantity',
    warehouse_code VARCHAR(20) NULL COMMENT 'Destination warehouse code',
    from_warehouse_code VARCHAR(20) NULL COMMENT 'Source warehouse code',
    remaining_open_quantity DECIMAL(15,4) NULL COMMENT 'SAP RemainingOpenInventoryQuantity',
    line_status VARCHAR(20) NULL COMMENT 'Line status (bost_Open/bost_Close)',
    uom_code VARCHAR(20) NULL COMMENT 'Unit of measure code',
    -- WMS tracking fields
    transferred_quantity DECIMAL(15,4) DEFAULT 0 COMMENT 'Quantity transferred via WMS',
    wms_remaining_quantity DECIMAL(15,4) NULL COMMENT 'WMS calculated remaining quantity',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_transfer_id) REFERENCES inventory_transfers(id) ON DELETE CASCADE,
    INDEX idx_inventory_transfer_id (inventory_transfer_id),
    INDEX idx_item_code (item_code),
    INDEX idx_sap_doc_entry (sap_doc_entry),
    INDEX idx_line_status (line_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores SAP B1 StockTransferLines exactly as received for later posting';
"""

CREATE_MIGRATION_TRACKING = """
CREATE TABLE IF NOT EXISTS wms_migrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    migration_name VARCHAR(100) NOT NULL UNIQUE,
    migration_date VARCHAR(20) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'completed',
    notes TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def get_mysql_connection_string():
    """Get MySQL connection string from environment or config."""
    mysql_url = os.environ.get('MYSQL_DATABASE_URL')
    if mysql_url:
        return mysql_url
    
    host = os.environ.get('MYSQL_HOST', 'localhost')
    port = os.environ.get('MYSQL_PORT', '3306')
    user = os.environ.get('MYSQL_USER', 'root')
    password = os.environ.get('MYSQL_PASSWORD', '')
    database = os.environ.get('MYSQL_DATABASE', 'wms')
    
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as cnt FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = '{table_name}' 
                AND COLUMN_NAME = '{column_name}'
            """))
            row = result.fetchone()
            return row[0] > 0 if row else False
    except Exception as e:
        logger.warning(f"Could not check column {table_name}.{column_name}: {e}")
        return False


def check_table_exists(engine, table_name):
    """Check if a table exists."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as cnt FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = '{table_name}'
            """))
            row = result.fetchone()
            return row[0] > 0 if row else False
    except Exception as e:
        logger.warning(f"Could not check table {table_name}: {e}")
        return False


def check_migration_applied(engine, migration_name):
    """Check if migration was already applied."""
    try:
        if not check_table_exists(engine, 'wms_migrations'):
            return False
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT COUNT(*) as cnt FROM wms_migrations 
                WHERE migration_name = '{migration_name}'
            """))
            row = result.fetchone()
            return row[0] > 0 if row else False
    except Exception as e:
        logger.warning(f"Could not check migration status: {e}")
        return False


def record_migration(engine, migration_name, migration_date, notes=""):
    """Record that a migration was applied."""
    try:
        with engine.connect() as conn:
            conn.execute(text(f"""
                INSERT INTO wms_migrations (migration_name, migration_date, notes)
                VALUES ('{migration_name}', '{migration_date}', '{notes}')
                ON DUPLICATE KEY UPDATE applied_at = CURRENT_TIMESTAMP, notes = '{notes}'
            """))
            conn.commit()
        logger.info(f"Recorded migration: {migration_name}")
    except Exception as e:
        logger.warning(f"Could not record migration: {e}")


def run_migration():
    """Execute the migration."""
    logger.info("=" * 70)
    logger.info("MySQL Migration: Inventory Transfer SAP B1 Persistent Storage")
    logger.info(f"Migration Date: {MIGRATION_DATE}")
    logger.info("=" * 70)
    
    connection_string = get_mysql_connection_string()
    
    try:
        engine = create_engine(connection_string, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Successfully connected to MySQL database")
    except OperationalError as e:
        logger.error(f"Could not connect to MySQL database: {e}")
        logger.info("Please set MYSQL_DATABASE_URL or individual MYSQL_* environment variables")
        return False
    
    try:
        with engine.connect() as conn:
            conn.execute(text(CREATE_MIGRATION_TRACKING))
            conn.commit()
    except Exception as e:
        logger.warning(f"Could not create migration tracking table: {e}")
    
    if check_migration_applied(engine, MIGRATION_NAME):
        logger.info(f"Migration '{MIGRATION_NAME}' was already applied. Skipping.")
        return True
    
    success = True
    changes_made = []
    
    logger.info("\n--- Step 1: Adding SAP fields to inventory_transfers table ---")
    for column_name, alter_sql in ALTER_INVENTORY_TRANSFERS_INDIVIDUAL:
        if check_column_exists(engine, 'inventory_transfers', column_name):
            logger.info(f"  Column 'inventory_transfers.{column_name}' already exists. Skipping.")
        else:
            try:
                with engine.connect() as conn:
                    conn.execute(text(alter_sql))
                    conn.commit()
                logger.info(f"  Added column 'inventory_transfers.{column_name}'")
                changes_made.append(f"Added inventory_transfers.{column_name}")
            except Exception as e:
                logger.error(f"  Failed to add column 'inventory_transfers.{column_name}': {e}")
                success = False
    
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX idx_sap_doc_entry ON inventory_transfers(sap_doc_entry)"))
            conn.commit()
        logger.info("  Added index idx_sap_doc_entry on inventory_transfers")
        changes_made.append("Added index idx_sap_doc_entry")
    except Exception as e:
        if "Duplicate key name" in str(e) or "already exists" in str(e).lower():
            logger.info("  Index idx_sap_doc_entry already exists. Skipping.")
        else:
            logger.warning(f"  Could not add index: {e}")
    
    logger.info("\n--- Step 2: Adding SAP fields to inventory_transfer_items table ---")
    for column_name, alter_sql in ALTER_INVENTORY_TRANSFER_ITEMS_INDIVIDUAL:
        if check_column_exists(engine, 'inventory_transfer_items', column_name):
            logger.info(f"  Column 'inventory_transfer_items.{column_name}' already exists. Skipping.")
        else:
            try:
                with engine.connect() as conn:
                    conn.execute(text(alter_sql))
                    conn.commit()
                logger.info(f"  Added column 'inventory_transfer_items.{column_name}'")
                changes_made.append(f"Added inventory_transfer_items.{column_name}")
            except Exception as e:
                logger.error(f"  Failed to add column 'inventory_transfer_items.{column_name}': {e}")
                success = False
    
    logger.info("\n--- Step 3: Creating inventory_transfer_request_lines table ---")
    if check_table_exists(engine, 'inventory_transfer_request_lines'):
        logger.info("  Table 'inventory_transfer_request_lines' already exists. Skipping.")
    else:
        try:
            with engine.connect() as conn:
                conn.execute(text(CREATE_INVENTORY_TRANSFER_REQUEST_LINES))
                conn.commit()
            logger.info("  Created table 'inventory_transfer_request_lines'")
            changes_made.append("Created inventory_transfer_request_lines table")
        except Exception as e:
            logger.error(f"  Failed to create table 'inventory_transfer_request_lines': {e}")
            success = False
    
    if success:
        notes = "; ".join(changes_made) if changes_made else "No changes needed - all objects already exist"
        record_migration(engine, MIGRATION_NAME, MIGRATION_DATE, notes)
        logger.info("\n" + "=" * 70)
        logger.info("Migration completed successfully!")
        logger.info("=" * 70)
        if changes_made:
            logger.info("\nChanges made:")
            for change in changes_made:
                logger.info(f"  - {change}")
        else:
            logger.info("\nNo changes were needed - all database objects already exist.")
    else:
        logger.error("\n" + "=" * 70)
        logger.error("Migration completed with errors. Please review the log above.")
        logger.error("=" * 70)
    
    return success


def rollback_migration():
    """Rollback the migration (for development/testing only)."""
    logger.warning("=" * 70)
    logger.warning("ROLLBACK: Inventory Transfer SAP B1 Persistent Storage")
    logger.warning("WARNING: This will remove columns and tables. Data will be LOST!")
    logger.warning("=" * 70)
    
    confirm = input("Type 'YES' to confirm rollback: ")
    if confirm != 'YES':
        logger.info("Rollback cancelled.")
        return False
    
    connection_string = get_mysql_connection_string()
    
    try:
        engine = create_engine(connection_string, echo=False)
    except Exception as e:
        logger.error(f"Could not connect to MySQL database: {e}")
        return False
    
    rollback_statements = [
        "DROP TABLE IF EXISTS inventory_transfer_request_lines",
        "ALTER TABLE inventory_transfer_items DROP COLUMN IF EXISTS line_status",
        "ALTER TABLE inventory_transfer_items DROP COLUMN IF EXISTS sap_doc_entry",
        "ALTER TABLE inventory_transfer_items DROP COLUMN IF EXISTS sap_line_num",
        "ALTER TABLE inventory_transfer_items DROP COLUMN IF EXISTS to_warehouse_code",
        "ALTER TABLE inventory_transfer_items DROP COLUMN IF EXISTS from_warehouse_code",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS sap_raw_json",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS due_date",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS doc_date",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS sap_document_status",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS bpl_name",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS bpl_id",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS sap_doc_num",
        "ALTER TABLE inventory_transfers DROP COLUMN IF EXISTS sap_doc_entry",
        f"DELETE FROM wms_migrations WHERE migration_name = '{MIGRATION_NAME}'",
    ]
    
    for stmt in rollback_statements:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
            logger.info(f"Executed: {stmt[:60]}...")
        except Exception as e:
            logger.warning(f"Could not execute: {stmt[:60]}... Error: {e}")
    
    logger.info("Rollback completed.")
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        rollback_migration()
    else:
        success = run_migration()
        sys.exit(0 if success else 1)
