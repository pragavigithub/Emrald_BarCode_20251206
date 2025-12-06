"""
Multiple GRN Creation Module Models
Database models for batch GRN creation from multiple POs

STATUS WORKFLOW (QC Approval Required):
--------------------------------------
1. draft       - Batch being created, items being selected
2. submitted   - Batch submitted for QC approval (no SAP posting yet)
3. qc_approved - QC has approved the batch (internal status)
4. posted      - Consolidated GRN successfully posted to SAP B1
5. rejected    - QC has rejected the batch
6. failed      - SAP posting failed after QC approval

CRITICAL DESIGN:
- SAP posting happens ONLY through QC Dashboard after approval
- Multi GRN screen does NOT post to SAP directly
- Consolidated posting: Multiple POs → Single GRN document
"""
from app import db
from datetime import datetime

class MultiGRNBatch(db.Model):
    """
    Main batch record for multiple GRN creation
    
    Status Flow:
        draft → submitted → qc_approved → posted
               ↓
            rejected (if QC rejects)
    """
    __tablename__ = 'multi_grn_document'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_number = db.Column(db.String(50), unique=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    series_id = db.Column(db.Integer, nullable=True)
    series_name = db.Column(db.String(100), nullable=True)
    customer_code = db.Column(db.String(50), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='draft', nullable=False)
    total_pos = db.Column(db.Integer, default=0)
    total_grns_created = db.Column(db.Integer, default=0)
    sap_session_metadata = db.Column(db.Text)
    error_log = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Text)
    posted_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    submitted_at = db.Column(db.DateTime)
    qc_approver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    qc_approved_at = db.Column(db.DateTime)
    qc_notes = db.Column(db.Text)
    
    user = db.relationship('User', foreign_keys=[user_id], backref='multi_grn_document')
    qc_approver = db.relationship('User', foreign_keys=[qc_approver_id])
    po_links = db.relationship('MultiGRNPOLink', backref='batch', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<MultiGRNBatch {self.id} - {self.customer_name}>'

class MultiGRNPOLink(db.Model):
    """Links between GRN batch and selected Purchase Orders"""
    __tablename__ = 'multi_grn_po_links'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('multi_grn_document.id'), nullable=False)
    po_doc_entry = db.Column(db.Integer, nullable=False)
    po_doc_num = db.Column(db.String(50), nullable=False)
    po_card_code = db.Column(db.String(50))
    po_card_name = db.Column(db.String(200))
    po_doc_date = db.Column(db.Date)
    po_doc_total = db.Column(db.Numeric(15, 2))
    status = db.Column(db.String(20), default='selected', nullable=False)
    sap_grn_doc_num = db.Column(db.String(50))
    sap_grn_doc_entry = db.Column(db.Integer)
    posted_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    line_selections = db.relationship('MultiGRNLineSelection', backref='po_link', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('batch_id', 'po_doc_entry', name='uq_batch_po'),
    )
    
    def __repr__(self):
        return f'<MultiGRNPOLink PO:{self.po_doc_num}>'

class MultiGRNLineSelection(db.Model):
    """Selected line items from Purchase Orders"""
    __tablename__ = 'multi_grn_line_selections'
    
    id = db.Column(db.Integer, primary_key=True)
    po_link_id = db.Column(db.Integer, db.ForeignKey('multi_grn_po_links.id'), nullable=False)
    po_line_num = db.Column(db.Integer, nullable=False)
    item_code = db.Column(db.String(50), nullable=False)
    item_description = db.Column(db.String(200))
    ordered_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    open_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    selected_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    warehouse_code = db.Column(db.String(50))
    bin_location = db.Column(db.String(200))
    unit_price = db.Column(db.Numeric(15, 4))
    unit_of_measure = db.Column(db.String(10))
    line_status = db.Column(db.String(20))
    inventory_type = db.Column(db.String(20))
    serial_numbers = db.Column(db.Text)
    batch_numbers = db.Column(db.Text)
    posting_payload = db.Column(db.Text)
    barcode_generated = db.Column(db.Boolean, default=False)
    
    batch_required = db.Column(db.String(1), default='N')
    serial_required = db.Column(db.String(1), default='N')
    manage_method = db.Column(db.String(1), default='N')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    batch_details = db.relationship('MultiGRNBatchDetails', backref='line_selection', lazy=True, cascade='all, delete-orphan')
    serial_details = db.relationship('MultiGRNSerialDetails', backref='line_selection', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<MultiGRNLineSelection {self.item_code} - Qty:{self.selected_quantity}>'

class MultiGRNBatchDetails(db.Model):
    """Batch number details for Multi GRN line items (similar to GRPO)"""
    __tablename__ = 'multi_grn_batch_details'
    
    id = db.Column(db.Integer, primary_key=True)
    line_selection_id = db.Column(db.Integer, db.ForeignKey('multi_grn_line_selections.id'), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    manufacturer_serial_number = db.Column(db.String(100))
    internal_serial_number = db.Column(db.String(100))
    expiry_date = db.Column(db.String(100))
    barcode = db.Column(db.String(200))
    grn_number = db.Column(db.String(50))
    qty_per_pack = db.Column(db.Numeric(15, 3))
    no_of_packs = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MultiGRNBatchDetails {self.batch_number} - Qty:{self.quantity}>'

class MultiGRNSerialDetails(db.Model):
    """Serial number details for Multi GRN line items (similar to GRPO)"""
    __tablename__ = 'multi_grn_serial_details'
    
    id = db.Column(db.Integer, primary_key=True)
    line_selection_id = db.Column(db.Integer, db.ForeignKey('multi_grn_line_selections.id'), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False)
    manufacturer_serial_number = db.Column(db.String(100))
    internal_serial_number = db.Column(db.String(100))
    expiry_date = db.Column(db.Date)
    barcode = db.Column(db.String(200))
    grn_number = db.Column(db.String(50))
    qty_per_pack = db.Column(db.Numeric(15, 3), default=1)
    no_of_packs = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MultiGRNSerialDetails {self.serial_number}>'

class MultiGRNBatchDetailsLabel(db.Model):
    """Individual pack labels for batch items - links each QR label to unique GRN number
    
    This table solves the problem of tracking individual packs when no_of_packs > 1.
    Each record represents one physical QR label/pack with its own unique GRN number.
    
    Example: If batch_details has quantity=7 and no_of_packs=3:
        - Label 1: pack_number=1, qty_in_pack=3, grn_number=MGN-19-43-1-1
        - Label 2: pack_number=2, qty_in_pack=2, grn_number=MGN-19-43-1-2
        - Label 3: pack_number=3, qty_in_pack=2, grn_number=MGN-19-43-1-3
    """
    __tablename__ = 'multi_grn_batch_details_label'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_detail_id = db.Column(db.Integer, db.ForeignKey('multi_grn_batch_details.id'), nullable=False)
    pack_number = db.Column(db.Integer, nullable=False)
    qty_in_pack = db.Column(db.Numeric(15, 3), nullable=False)
    grn_number = db.Column(db.String(50), unique=True, nullable=False)
    barcode = db.Column(db.Text)
    qr_data = db.Column(db.Text)
    printed = db.Column(db.Boolean, default=False)
    printed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Text)
    
    batch_detail = db.relationship('MultiGRNBatchDetails', backref=db.backref('pack_labels', cascade='all, delete-orphan'))
    
    __table_args__ = (
        db.UniqueConstraint('batch_detail_id', 'pack_number', name='uq_batch_pack'),
    )
    
    def __repr__(self):
        return f'<MultiGRNBatchDetailsLabel Pack:{self.pack_number} GRN:{self.grn_number}>'
