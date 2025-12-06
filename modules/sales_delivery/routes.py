from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from modules.sales_delivery.models import DeliveryDocument, DeliveryItem
from sap_integration import SAPIntegration
from datetime import datetime
from pathlib import Path
import logging

# Use absolute path for template_folder to support PyInstaller .exe builds
sales_delivery_bp = Blueprint('sales_delivery', __name__, 
                              template_folder=str(Path(__file__).resolve().parent / 'templates'),
                              url_prefix='/sales_delivery')


@sales_delivery_bp.route('/')
@login_required
def index():
    """Main page for Sales Order Against Delivery with filtering, search and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_term = request.args.get('search', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    
    query = DeliveryDocument.query.filter_by(user_id=current_user.id)
    
    if search_term:
        query = query.filter(
            db.or_(
                DeliveryDocument.so_doc_num.ilike(f'%{search_term}%'),
                DeliveryDocument.card_name.ilike(f'%{search_term}%'),
                DeliveryDocument.card_code.ilike(f'%{search_term}%'),
                DeliveryDocument.sap_doc_num.ilike(f'%{search_term}%')
            )
        )
    
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d')
            query = query.filter(DeliveryDocument.created_at >= from_dt)
        except ValueError:
            pass
    
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d')
            to_dt = to_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(DeliveryDocument.created_at <= to_dt)
        except ValueError:
            pass
    
    query = query.order_by(DeliveryDocument.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    deliveries = pagination.items
    
    return render_template('sales_delivery/sales_delivery_index.html', 
                         deliveries=deliveries,
                         per_page=per_page,
                         search_term=search_term,
                         from_date=from_date,
                         to_date=to_date,
                         pagination=pagination)


@sales_delivery_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new delivery note from Sales Order"""
    if request.method == 'POST':
        so_series = request.form.get('so_series')
        print(so_series)
        so_doc_num = request.form.get('so_doc_num')
        print(so_doc_num)
        
        logging.info(f"📋 Creating delivery for SO Series: {so_series}, DocNum: {so_doc_num}")
        
        if not so_series or not so_doc_num:
            flash('Please select a series and enter a document number', 'error')
            return redirect(url_for('sales_delivery.index'))
        
        sap = SAPIntegration()
        
        logging.info(f"🔍 Getting DocEntry for SO Series: {so_series}, DocNum: {so_doc_num}")
        doc_entry = sap.get_so_doc_entry(so_series, so_doc_num)
        print(doc_entry)
        if not doc_entry:
            logging.error(f"❌ DocEntry not found for SO Series: {so_series}, DocNum: {so_doc_num}")
            flash(f'Sales Order {so_doc_num} not found in series {so_series}. Check SAP connection.', 'error')
            return redirect(url_for('sales_delivery.index'))
        
        logging.info(f"📥 Loading SO data for DocEntry: {doc_entry}")
        so_data = sap.get_sales_order_by_doc_entry(doc_entry)
        
        if not so_data:
            logging.error(f"❌ SO data not found for DocEntry: {doc_entry}")
            flash(f'Sales Order {so_doc_num} is not available or has no open lines', 'error')
            return redirect(url_for('sales_delivery.index'))
        
        logging.info(f"✅ SO data loaded: CardCode={so_data.get('CardCode')}, CardName={so_data.get('CardName')}, Lines={len(so_data.get('DocumentLines', []))}")
        
        existing = DeliveryDocument.query.filter_by(
            so_doc_entry=doc_entry,
            user_id=current_user.id,
            status='draft'
        ).first()
        
        if existing:
            return redirect(url_for('sales_delivery.detail', delivery_id=existing.id))
        
        delivery = DeliveryDocument(
            so_doc_entry=doc_entry,
            so_doc_num=so_data.get('DocNum'),
            so_series=so_data.get('Series'),
            card_code=so_data.get('CardCode'),
            card_name=so_data.get('CardName'),
            doc_currency=so_data.get('DocCurrency'),
            doc_date=datetime.now(),
            user_id=current_user.id
        )
        
        db.session.add(delivery)
        db.session.commit()
        
        flash(f'Sales Order {so_doc_num} loaded successfully', 'success')
        return redirect(url_for('sales_delivery.detail', delivery_id=delivery.id))
    
    return redirect(url_for('sales_delivery.index'))


@sales_delivery_bp.route('/detail/<int:delivery_id>')
@login_required
def detail(delivery_id):
    """Detail page for a delivery note"""
    delivery = DeliveryDocument.query.get_or_404(delivery_id)
    
    if delivery.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('sales_delivery.index'))
    
    sap = SAPIntegration()
    so_data = sap.get_sales_order_by_doc_entry(delivery.so_doc_entry)
    
    if not so_data:
        flash('Unable to load Sales Order details from SAP', 'error')
        return redirect(url_for('sales_delivery.index'))
    
    return render_template('sales_delivery/sales_delivery_detail.html', 
                         delivery=delivery,
                         so_data=so_data)


@sales_delivery_bp.route('/api/get_series')
@login_required
def api_get_series():
    """Get Sales Order series from SAP"""
    sap = SAPIntegration()
    series_list = sap.get_so_series()
    return jsonify({'success': True, 'series': series_list})


@sales_delivery_bp.route('/api/get_open_so_docnums')
@login_required
def api_get_open_so_docnums():
    """Get open Sales Order document numbers for a specific series"""
    series = request.args.get('series')
    
    if not series:
        return jsonify({'success': False, 'error': 'Series is required'})
    
    sap = SAPIntegration()
    documents = sap.get_open_so_docnums(series)
    
    return jsonify({'success': True, 'documents': documents})


@sales_delivery_bp.route('/api/validate_item', methods=['POST'])
@login_required
def api_validate_item():
    """Validate item code and get batch/serial requirements"""
    data = request.get_json()
    item_code = data.get('item_code')
    
    if not item_code:
        return jsonify({'success': False, 'error': 'Item code is required'})
    
    sap = SAPIntegration()
    validation = sap.validate_item_code(item_code)
    
    return jsonify(validation)


@sales_delivery_bp.route('/api/add_item', methods=['POST'])
@login_required
def api_add_item():
    """Add item to delivery document"""
    data = request.get_json()
    
    delivery_id = data.get('delivery_id')
    base_line = data.get('base_line')
    item_code = data.get('item_code')
    quantity = data.get('quantity')
    batch_number = data.get('batch_number')
    serial_number = data.get('serial_number')
    
    if not all([delivery_id, base_line is not None, item_code, quantity]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    delivery = DeliveryDocument.query.get(delivery_id)
    
    if not delivery or delivery.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'})
    
    sap = SAPIntegration()
    so_data = sap.get_sales_order_by_doc_entry(delivery.so_doc_entry)
    
    if not so_data:
        return jsonify({'success': False, 'error': 'Sales Order not found'})
    
    so_line = None
    for line in so_data.get('DocumentLines', []):
        if line.get('LineNum') == base_line:
            so_line = line
            break
    
    if not so_line:
        return jsonify({'success': False, 'error': 'Line not found in Sales Order'})
    
    validation = sap.validate_item_code(item_code)
    
    next_line_num = db.session.query(db.func.max(DeliveryItem.line_number)).filter_by(
        delivery_id=delivery_id
    ).scalar() or 0
    
    item = DeliveryItem(
        delivery_id=delivery_id,
        line_number=next_line_num + 1,
        base_line=base_line,
        item_code=item_code,
        item_description=so_line.get('ItemDescription'),
        warehouse_code=so_line.get('WarehouseCode'),
        quantity=float(quantity),
        open_quantity=so_line.get('RemainingOpenQuantity', 0),
        unit_price=so_line.get('UnitPrice', 0),
        uom_code=so_line.get('UoMCode'),
        batch_required=validation.get('batch_required', False),
        serial_required=validation.get('serial_required', False),
        batch_number=batch_number,
        serial_number=serial_number
    )
    
    db.session.add(item)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Item added successfully',
        'item_id': item.id
    })


@sales_delivery_bp.route('/api/submit_delivery', methods=['POST'])
@login_required
def api_submit_delivery():
    """Submit delivery note for QC approval (does not post to SAP yet)"""
    data = request.get_json()
    delivery_id = data.get('delivery_id')
    
    if not delivery_id:
        return jsonify({'success': False, 'error': 'Delivery ID is required'})
    
    delivery = DeliveryDocument.query.get(delivery_id)
    
    if not delivery or delivery.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'})
    
    if delivery.status != 'draft':
        return jsonify({'success': False, 'error': 'Delivery already submitted'})
    
    items = DeliveryItem.query.filter_by(delivery_id=delivery_id).all()
    
    if not items:
        return jsonify({'success': False, 'error': 'No items to deliver'})
    
    sap = SAPIntegration()
    
    # Validate we have all required data from SAP (but don't post yet)
    card_code = delivery.card_code
    doc_currency = delivery.doc_currency
    
    if not card_code:
        # Fetch from SAP if missing from delivery record
        logging.info(f"CardCode missing, fetching from SAP for DocEntry: {delivery.so_doc_entry}")
        so_data = sap.get_sales_order_by_doc_entry(delivery.so_doc_entry)
        if so_data:
            card_code = so_data.get('CardCode')
            if not doc_currency:
                doc_currency = so_data.get('DocCurrency', 'INR')
            # Update delivery record with missing data
            delivery.card_code = card_code
            delivery.card_name = so_data.get('CardName')
            delivery.doc_currency = doc_currency
            db.session.commit()
        else:
            return jsonify({'success': False, 'error': 'Unable to fetch Sales Order details from SAP'})
    
    # Submit for QC approval without posting to SAP
    delivery.status = 'submitted'
    delivery.submitted_at = datetime.utcnow()
    db.session.commit()
    
    logging.info(f"✅ Sales Delivery {delivery_id} submitted for QC approval by {current_user.username}")
    
    return jsonify({
        'success': True,
        'message': f'Delivery against SO {delivery.so_doc_num} submitted for QC approval'
    })


@sales_delivery_bp.route('/api/approve_delivery', methods=['POST'])
@login_required
def api_approve_delivery():
    """QC approve delivery and post to SAP B1"""
    try:
        data = request.get_json()
        delivery_id = data.get('delivery_id')
        
        if not delivery_id:
            return jsonify({'success': False, 'error': 'Delivery ID is required'})
        
        delivery = DeliveryDocument.query.get(delivery_id)
        
        if not delivery:
            return jsonify({'success': False, 'error': 'Delivery not found'})
        
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if delivery.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted deliveries can be approved'})
        
        qc_notes = data.get('qc_notes', '')
        
        delivery.status = 'qc_approved'
        delivery.qc_approver_id = current_user.id
        delivery.qc_approved_at = datetime.utcnow()
        delivery.qc_notes = qc_notes
        
        for item in delivery.items:
            item.qc_status = 'approved'
        
        sap = SAPIntegration()
        
        if not sap.ensure_logged_in():
            db.session.rollback()
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500
        
        document_lines = []
        for item in delivery.items:
            doc_line = {
                'BaseType': 17,
                'BaseEntry': delivery.so_doc_entry,
                'BaseLine': item.base_line,
                'ItemCode': item.item_code,
                'Quantity': item.quantity,
                'WarehouseCode': item.warehouse_code
            }
            
            if item.batch_required and item.batch_number:
                doc_line['BatchNumbers'] = [{
                    'BatchNumber': item.batch_number,
                    'Quantity': item.quantity
                }]
            
            if item.serial_required and item.serial_number:
                doc_line['SerialNumbers'] = [{
                    'InternalSerialNumber': item.serial_number,
                    'Quantity': 1.0
                }]
            
            document_lines.append(doc_line)
        
        delivery_data = {
            'CardCode': delivery.card_code,
            'DocDate': datetime.now().strftime('%Y-%m-%d'),
            'DocCurrency': delivery.doc_currency or 'INR',
            'Comments': f'QC Approved - SO {delivery.so_doc_num}',
            'DocumentLines': document_lines
        }
        
        result = sap.post_sales_delivery(delivery_data)
        
        if not result.get('success'):
            db.session.rollback()
            error_msg = result.get('error', 'Unknown SAP error')
            logging.error(f"❌ SAP B1 posting failed for delivery {delivery_id}: {error_msg}")
            return jsonify({'success': False, 'error': f'SAP B1 posting failed: {error_msg}'}), 500
        
        delivery.sap_doc_entry = result.get('doc_entry')
        delivery.sap_doc_num = result.get('doc_num')
        delivery.status = 'posted'
        
        db.session.commit()
        
        logging.info(f"✅ Sales Delivery {delivery_id} approved and posted to SAP B1 as {delivery.sap_doc_num}")
        return jsonify({
            'success': True,
            'message': f'Delivery approved and posted to SAP B1 as {delivery.sap_doc_num}',
            'sap_doc_num': delivery.sap_doc_num
        })
        
    except Exception as e:
        logging.error(f"Error approving delivery: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@sales_delivery_bp.route('/api/reject_delivery', methods=['POST'])
@login_required
def api_reject_delivery():
    """QC reject delivery"""
    try:
        data = request.get_json()
        delivery_id = data.get('delivery_id')
        
        if not delivery_id:
            return jsonify({'success': False, 'error': 'Delivery ID is required'})
        
        delivery = DeliveryDocument.query.get(delivery_id)
        
        if not delivery:
            return jsonify({'success': False, 'error': 'Delivery not found'})
        
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if delivery.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted deliveries can be rejected'})
        
        qc_notes = data.get('qc_notes', '')
        
        if not qc_notes:
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400
        
        delivery.status = 'rejected'
        delivery.qc_approver_id = current_user.id
        delivery.qc_approved_at = datetime.utcnow()
        delivery.qc_notes = qc_notes
        
        for item in delivery.items:
            item.qc_status = 'rejected'
        
        db.session.commit()
        
        logging.info(f"❌ Sales Delivery {delivery_id} rejected by {current_user.username}")
        return jsonify({'success': True, 'message': 'Delivery rejected by QC'})
        
    except Exception as e:
        logging.error(f"Error rejecting delivery: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@sales_delivery_bp.route('/api/delete_item/<int:item_id>', methods=['DELETE'])
@login_required
def api_delete_item(item_id):
    """Delete item from delivery"""
    item = DeliveryItem.query.get_or_404(item_id)
    
    if item.delivery.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'})
    
    if item.delivery.status != 'draft':
        return jsonify({'success': False, 'error': 'Cannot delete from submitted delivery'})
    
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Item deleted successfully'})
