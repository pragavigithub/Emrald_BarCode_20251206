"""
Models for SO Against Invoice Module
"""
from datetime import datetime
from app import db
from flask_login import UserMixin


class SOInvoiceDocument(db.Model):
    """SO Against Invoice Document Header"""
    __tablename__ = 'so_invoice_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    document_number = db.Column(db.String(50), nullable=False, unique=True)
    sap_invoice_number = db.Column(db.String(50))  # SAP B1 generated invoice number
    so_series = db.Column(db.Integer, nullable=True)  # Selected SO Series
    so_series_name = db.Column(db.String(100), nullable=True)  # Series name for display
    so_number = db.Column(db.String(50), nullable=True)  # Entered SO Number
    so_doc_entry = db.Column(db.Integer, nullable=True)  # SAP B1 DocEntry of SO
    
    # Customer details from SO
    card_code = db.Column(db.String(50), nullable=True)
    card_name = db.Column(db.String(200), nullable=True)
    customer_address = db.Column(db.Text)
    
    # Invoice details
    doc_date = db.Column(db.DateTime, default=datetime.utcnow)
    doc_due_date = db.Column(db.DateTime)
    bplid = db.Column(db.Integer)  # Branch/Plant ID
    userSign=db.Column(db.Integer)
    
    status = db.Column(db.String(20), default='draft')  # draft, validated, posted, failed
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Comments and tracking
    comments = db.Column(db.Text)
    validation_notes = db.Column(db.Text)
    posting_error = db.Column(db.Text)  # Error details if posting fails
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='so_invoices')
    items = db.relationship('SOInvoiceItem', backref='so_invoice', lazy=True, cascade='all, delete-orphan')


class SOInvoiceItem(db.Model):
    """SO Against Invoice Line Items"""
    __tablename__ = 'so_invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    so_invoice_id = db.Column(db.Integer, db.ForeignKey('so_invoice_documents.id'), nullable=False)
    line_num = db.Column(db.Integer, nullable=False)  # Original line number from SO
    
    # Item details from SO
    item_code = db.Column(db.String(50), nullable=False)
    item_description = db.Column(db.String(200), nullable=False)
    so_quantity = db.Column(db.Float, nullable=False)  # Original quantity from SO
    warehouse_code = db.Column(db.String(10), nullable=False)
    
    # Validated item details
    validated_quantity = db.Column(db.Float, default=0)  # Quantity validated for invoice
    is_serial_managed = db.Column(db.Boolean, default=False)
    is_batch_managed = db.Column(db.Boolean, default=False)
    
    validation_status = db.Column(db.String(20), default='pending')  # pending, validated, failed
    validation_error = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    serial_numbers = db.relationship('SOInvoiceSerial', backref='invoice_item', lazy=True, cascade='all, delete-orphan')


class SOInvoiceSerial(db.Model):
    """Serial Numbers for SO Invoice Items"""
    __tablename__ = 'so_invoice_serials'
    
    id = db.Column(db.Integer, primary_key=True)
    so_invoice_item_id = db.Column(db.Integer, db.ForeignKey('so_invoice_items.id'), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    base_line_number = db.Column(db.Integer, nullable=False)  # Line number for SAP B1 posting
    
    validation_status = db.Column(db.String(20), default='pending')  # pending, validated, failed
    validation_error = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Prevent duplicate serial numbers within the same invoice
    __table_args__ = (db.UniqueConstraint('so_invoice_item_id', 'serial_number', name='unique_serial_per_invoice_item'),)


class SOSeries(db.Model):
    """SO Series Cache for faster lookup"""
    __tablename__ = 'so_series_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    series = db.Column(db.Integer, nullable=False, unique=True)
    series_name = db.Column(db.String(100), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)