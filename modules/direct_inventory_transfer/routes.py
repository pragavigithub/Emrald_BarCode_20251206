from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import logging
import json
from pathlib import Path

from app import db
from models import DirectInventoryTransfer, DirectInventoryTransferItem, DocumentNumberSeries
from sap_integration import SAPIntegration

# Use absolute path for template_folder to support PyInstaller .exe builds
direct_inventory_transfer_bp = Blueprint('direct_inventory_transfer', __name__, 
                                         url_prefix='/direct-inventory-transfer',
                                         template_folder=str(Path(__file__).resolve().parent / 'templates'))


def generate_direct_transfer_number():
    """Generate unique transfer number for Direct Inventory Transfer"""
    return DocumentNumberSeries.get_next_number('DIRECT_INVENTORY_TRANSFER')


@direct_inventory_transfer_bp.route('/', methods=['GET'])
@login_required
def index():
    """Direct Inventory Transfer main page with filtering, search, and pagination"""
    if not current_user.has_permission('direct_inventory_transfer'):
        flash('Access denied - Direct Inventory Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search_term = request.args.get('search', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    status_filter = request.args.get('status', '').strip()
    
    if per_page not in [5, 10, 25, 50, 100]:
        per_page = 10

    query = DirectInventoryTransfer.query

    if current_user.role not in ['admin', 'manager']:
        query = query.filter_by(user_id=current_user.id)

    if search_term:
        search_pattern = f'%{search_term}%'
        query = query.filter(
            db.or_(
                DirectInventoryTransfer.transfer_number.ilike(search_pattern),
                DirectInventoryTransfer.from_warehouse.ilike(search_pattern),
                DirectInventoryTransfer.to_warehouse.ilike(search_pattern),
                DirectInventoryTransfer.notes.ilike(search_pattern)
            )
        )
    
    if status_filter:
        query = query.filter(DirectInventoryTransfer.status == status_filter)
    
    if from_date:
        query = query.filter(DirectInventoryTransfer.created_at >= from_date)
    
    if to_date:
        query = query.filter(DirectInventoryTransfer.created_at <= f"{to_date} 23:59:59")

    query = query.order_by(DirectInventoryTransfer.created_at.desc())
    transfers_paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('direct_inventory_transfer/index.html',
                           transfers=transfers_paginated.items,
                           pagination=transfers_paginated,
                           per_page=per_page,
                           search_term=search_term,
                           from_date=from_date,
                           to_date=to_date,
                           status_filter=status_filter,
                           current_user=current_user)


@direct_inventory_transfer_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new Direct Inventory Transfer with first item included"""
    if not current_user.has_permission('direct_inventory_transfer'):
        flash('Access denied - Direct Inventory Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            transfer_number = generate_direct_transfer_number()
            
            item_code = request.form.get('item_code', '').strip()
            item_type = request.form.get('item_type', 'none')
            quantity = float(request.form.get('quantity', 1))
            from_warehouse = request.form.get('from_warehouse')
            to_warehouse = request.form.get('to_warehouse')
            from_bin = request.form.get('from_bin', '')
            to_bin = request.form.get('to_bin', '')
            notes = request.form.get('notes', '')
            serial_numbers_str = request.form.get('serial_numbers', '').strip()
            batch_number = request.form.get('batch_number', '').strip()

            if not all([item_code, from_warehouse, to_warehouse]):
                flash('Item Code, From Warehouse and To Warehouse are required', 'error')
                return render_template('direct_inventory_transfer/create.html')

            if from_warehouse == to_warehouse:
                flash('From Warehouse and To Warehouse must be different', 'error')
                return render_template('direct_inventory_transfer/create.html')

            sap = SAPIntegration()
            if not sap.ensure_logged_in():
                flash('SAP B1 authentication failed', 'error')
                return render_template('direct_inventory_transfer/create.html')

            validation_result = sap.validate_item_for_direct_transfer(item_code)
            
            if not validation_result.get('valid'):
                flash(f'Item validation failed: {validation_result.get("error", "Unknown error")}', 'error')
                return render_template('direct_inventory_transfer/create.html')

            item_type_validated = validation_result.get('item_type', 'none')
            is_serial_managed = validation_result.get('is_serial_managed', False)
            is_batch_managed = validation_result.get('is_batch_managed', False)

            serial_numbers_json = None
            serial_numbers_list = []
            
            if is_serial_managed:
                if not serial_numbers_str:
                    flash('Serial numbers are required for serial-managed items', 'error')
                    return render_template('direct_inventory_transfer/create.html')
                
                serial_numbers_list = [sn.strip() for sn in serial_numbers_str.split(',') if sn.strip()]
                
                if len(serial_numbers_list) != int(quantity):
                    flash(f'Number of serial numbers ({len(serial_numbers_list)}) must match quantity ({int(quantity)})', 'error')
                    return render_template('direct_inventory_transfer/create.html')
                
                serial_numbers_json = json.dumps(serial_numbers_list)
            
            elif is_batch_managed:
                if not batch_number:
                    flash('Batch number is required for batch-managed items', 'error')
                    return render_template('direct_inventory_transfer/create.html')

            transfer = DirectInventoryTransfer(
                transfer_number=transfer_number,
                user_id=current_user.id,
                from_warehouse=from_warehouse,
                to_warehouse=to_warehouse,
                from_bin=from_bin,
                to_bin=to_bin,
                notes=notes,
                status='draft'
            )

            db.session.add(transfer)
            db.session.flush()

            transfer_item = DirectInventoryTransferItem(
                direct_inventory_transfer_id=transfer.id,
                item_code=validation_result.get('item_code'),
                item_description=validation_result.get('item_description'),
                barcode=item_code,
                item_type=item_type_validated,
                quantity=quantity,
                from_warehouse_code=from_warehouse,
                to_warehouse_code=to_warehouse,
                from_bin_code=from_bin,
                to_bin_code=to_bin,
                batch_number=batch_number if is_batch_managed else None,
                serial_numbers=serial_numbers_json,
                validation_status='validated',
                qc_status='pending'
            )

            db.session.add(transfer_item)
            db.session.commit()

            flash(f'Direct Inventory Transfer {transfer_number} created successfully with item {item_code}', 'success')
            return redirect(url_for('direct_inventory_transfer.detail', transfer_id=transfer.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error creating direct inventory transfer: {str(e)}")
            flash(f'Error creating transfer: {str(e)}', 'error')
            return render_template('direct_inventory_transfer/create.html')

    return render_template('direct_inventory_transfer/create.html')


@direct_inventory_transfer_bp.route('/<int:transfer_id>', methods=['GET'])
@login_required
def detail(transfer_id):
    """Direct Inventory Transfer detail page"""
    transfer = DirectInventoryTransfer.query.get_or_404(transfer_id)

    if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager', 'qc']:
        flash('Access denied - You can only view your own transfers', 'error')
        return redirect(url_for('direct_inventory_transfer.index'))

    return render_template('direct_inventory_transfer/detail.html', transfer=transfer)


@direct_inventory_transfer_bp.route('/api/get-warehouses', methods=['GET'])
@login_required
def get_warehouses():
    """Get warehouse list from SAP B1"""
    try:
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        warehouses = sap.get_warehouses()
        return jsonify({'success': True, 'warehouses': warehouses})

    except Exception as e:
        logging.error(f"Error fetching warehouses: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/get-bins', methods=['GET'])
@login_required
def get_bins():
    """Get bin list for a warehouse from SAP B1"""
    try:
        warehouse_code = request.args.get('warehouse_code')
        
        if not warehouse_code:
            return jsonify({'success': False, 'error': 'Warehouse code is required'}), 400

        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        bins = sap.get_bins(warehouse_code)
        return jsonify({'success': True, 'bins': bins})

    except Exception as e:
        logging.error(f"Error fetching bins: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/get-bin-locations', methods=['GET'])
@login_required
def get_bin_locations():
    """Get bin locations for a warehouse using SQL Query GetBinCodeByWHCode"""
    try:
        warehouse_code = request.args.get('warehouse_code')
        
        if not warehouse_code:
            return jsonify({'success': False, 'error': 'Warehouse code is required'}), 400

        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        result = sap.get_bin_locations_list(warehouse_code)
        return jsonify(result)

    except Exception as e:
        logging.error(f"Error fetching bin locations: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/validate-item', methods=['POST'])
@login_required
def validate_item():
    """Validate item by barcode/item code and get serial/batch management info"""
    try:
        item_code = request.form.get('item_code', '').strip()
        
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400

        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        validation_result = sap.validate_item_for_direct_transfer(item_code)
        
        if not validation_result.get('valid'):
            return jsonify({
                'success': False,
                'error': validation_result.get('error', 'Item validation failed')
            }), 400

        return jsonify({
            'success': True,
            'item_code': validation_result.get('item_code'),
            'item_description': validation_result.get('item_description'),
            'item_type': validation_result.get('item_type'),  # 'serial', 'batch', or 'none'
            'is_serial_managed': validation_result.get('is_serial_managed'),
            'is_batch_managed': validation_result.get('is_batch_managed')
        })

    except Exception as e:
        logging.error(f"Error validating item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/<int:transfer_id>/add_item', methods=['POST'])
@login_required
def add_item(transfer_id):
    """Add item to Direct Inventory Transfer with SAP validation"""
    try:
        transfer = DirectInventoryTransfer.query.get_or_404(transfer_id)

        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add items to non-draft transfer'}), 400

        item_code = request.form.get('item_code', '').strip()
        item_type = request.form.get('item_type', 'none')
        quantity = float(request.form.get('quantity', 1))
        serial_numbers_str = request.form.get('serial_numbers', '').strip()
        batch_number = request.form.get('batch_number', '').strip()

        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400

        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        validation_result = sap.validate_item_for_direct_transfer(item_code)
        
        if not validation_result.get('valid'):
            return jsonify({
                'success': False,
                'error': validation_result.get('error', 'Item validation failed')
            }), 400

        item_type_validated = validation_result.get('item_type', 'none')
        is_serial_managed = validation_result.get('is_serial_managed', False)
        is_batch_managed = validation_result.get('is_batch_managed', False)

        serial_numbers_json = None
        serial_numbers_list = []
        
        if is_serial_managed:
            if not serial_numbers_str:
                return jsonify({'success': False, 'error': 'Serial numbers are required for serial-managed items'}), 400
            
            serial_numbers_list = [sn.strip() for sn in serial_numbers_str.split(',') if sn.strip()]
            
            if len(serial_numbers_list) != int(quantity):
                return jsonify({'success': False, 'error': f'Number of serial numbers ({len(serial_numbers_list)}) must match quantity ({int(quantity)})'}), 400
            
            serial_numbers_json = json.dumps(serial_numbers_list)
        
        elif is_batch_managed:
            if not batch_number:
                return jsonify({'success': False, 'error': 'Batch number is required for batch-managed items'}), 400

        transfer_item = DirectInventoryTransferItem(
            direct_inventory_transfer_id=transfer.id,
            item_code=validation_result.get('item_code'),
            item_description=validation_result.get('item_description', ''),
            barcode=item_code,
            item_type=item_type_validated,
            quantity=quantity,
            from_warehouse_code=transfer.from_warehouse,
            to_warehouse_code=transfer.to_warehouse,
            from_bin_code=transfer.from_bin,
            to_bin_code=transfer.to_bin,
            batch_number=batch_number if is_batch_managed else None,
            serial_numbers=serial_numbers_json,
            validation_status='validated'
        )

        db.session.add(transfer_item)
        db.session.commit()

        logging.info(f"✅ Item {item_code} added to transfer {transfer_id}")

        return jsonify({
            'success': True,
            'message': f'Item {item_code} added successfully',
            'item_data': {
                'id': transfer_item.id,
                'item_code': transfer_item.item_code,
                'item_description': transfer_item.item_description,
                'item_type': transfer_item.item_type,
                'quantity': transfer_item.quantity,
                'batch_number': transfer_item.batch_number,
                'serial_numbers': json.loads(transfer_item.serial_numbers) if transfer_item.serial_numbers else []
            }
        })

    except Exception as e:
        logging.error(f"Error adding item: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    """Delete item from transfer"""
    try:
        item = DirectInventoryTransferItem.query.get_or_404(item_id)
        transfer = item.direct_inventory_transfer

        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot delete items from non-draft transfer'}), 400

        transfer_id = transfer.id
        item_code = item.item_code

        db.session.delete(item)
        db.session.commit()

        logging.info(f"🗑️ Item {item_code} deleted from transfer {transfer_id}")
        return jsonify({'success': True, 'message': f'Item {item_code} deleted'})

    except Exception as e:
        logging.error(f"Error deleting item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/<int:transfer_id>/submit', methods=['POST'])
@login_required
def submit_transfer(transfer_id):
    """Submit Direct Inventory Transfer for QC approval"""
    try:
        transfer = DirectInventoryTransfer.query.get_or_404(transfer_id)

        if transfer.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        if transfer.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft transfers can be submitted'}), 400

        if not transfer.items:
            return jsonify({'success': False, 'error': 'Cannot submit transfer without items'}), 400

        transfer.status = 'submitted'
        transfer.updated_at = datetime.utcnow()

        db.session.commit()

        logging.info(f"📤 Direct Inventory Transfer {transfer_id} submitted for QC approval")
        return jsonify({'success': True, 'message': 'Transfer submitted for QC approval'})

    except Exception as e:
        logging.error(f"Error submitting transfer: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/<int:transfer_id>/approve', methods=['POST'])
@login_required
def approve_transfer(transfer_id):
    """Approve Direct Inventory Transfer and post to SAP B1"""
    try:
        transfer = DirectInventoryTransfer.query.get_or_404(transfer_id)

        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403

        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be approved'}), 400

        qc_notes = request.json.get('qc_notes', '') if request.is_json else request.form.get('qc_notes', '')

        transfer.status = 'qc_approved'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        transfer.updated_at = datetime.utcnow()

        for item in transfer.items:
            item.qc_status = 'approved'

        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            db.session.rollback()
            return jsonify({'success': False, 'error': 'SAP B1 authentication failed'}), 500

        sap_result = sap.post_direct_inventory_transfer_to_sap(transfer)

        if not sap_result.get('success'):
            db.session.rollback()
            sap_error = sap_result.get('error', 'Unknown SAP error')
            logging.error(f"❌ SAP B1 posting failed: {sap_error}")
            return jsonify({'success': False, 'error': f'SAP B1 posting failed: {sap_error}'}), 500

        transfer.sap_document_number = sap_result.get('document_number')
        transfer.status = 'posted'
        
        db.session.commit()

        logging.info(f"✅ Direct Inventory Transfer {transfer_id} approved and posted to SAP B1 as {transfer.sap_document_number}")
        return jsonify({
            'success': True,
            'message': f'Transfer approved and posted to SAP B1 as {transfer.sap_document_number}',
            'sap_document_number': transfer.sap_document_number
        })

    except Exception as e:
        logging.error(f"Error approving transfer: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/<int:transfer_id>/reject', methods=['POST'])
@login_required
def reject_transfer(transfer_id):
    """Reject Direct Inventory Transfer"""
    try:
        transfer = DirectInventoryTransfer.query.get_or_404(transfer_id)

        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403

        if transfer.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted transfers can be rejected'}), 400

        qc_notes = request.json.get('qc_notes', '') if request.is_json else request.form.get('qc_notes', '')
        
        if not qc_notes:
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400

        transfer.status = 'rejected'
        transfer.qc_approver_id = current_user.id
        transfer.qc_approved_at = datetime.utcnow()
        transfer.qc_notes = qc_notes
        transfer.updated_at = datetime.utcnow()

        for item in transfer.items:
            item.qc_status = 'rejected'

        db.session.commit()

        logging.info(f"❌ Direct Inventory Transfer {transfer_id} rejected by {current_user.username}")
        return jsonify({'success': True, 'message': 'Transfer rejected by QC'})

    except Exception as e:
        logging.error(f"Error rejecting transfer: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/qr-scan', methods=['GET'])
@login_required
def qr_scan():
    """QR Code Scanning page for direct inventory transfer"""
    if not current_user.has_permission('direct_inventory_transfer'):
        flash('Access denied - Direct Inventory Transfer permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('direct_inventory_transfer.html')


@direct_inventory_transfer_bp.route('/api/decode-qr', methods=['POST'])
@login_required
def decode_qr():
    """Decode QR code JSON data"""
    try:
        data = request.get_json()
        qr_data_str = data.get('qr_data', '').strip()
        
        if not qr_data_str:
            return jsonify({'success': False, 'error': 'QR code data is required'}), 400
        
        qr_data = json.loads(qr_data_str)
        
        required_fields = ['item', 'qty']
        missing_fields = [field for field in required_fields if field not in qr_data]
        
        if missing_fields:
            return jsonify({
                'success': False, 
                'error': f'Missing required fields in QR code: {", ".join(missing_fields)}'
            }), 400
        
        return jsonify({
            'success': True,
            'item_code': qr_data.get('item'),
            'quantity': qr_data.get('qty'),
            'batch_number': qr_data.get('batch'),
            'po_number': qr_data.get('po'),
            'grn_id': qr_data.get('id'),
            'grn_date': qr_data.get('grn_date'),
            'exp_date': qr_data.get('exp_date'),
            'pack': qr_data.get('pack')
        })
        
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid QR code format: {str(e)}'}), 400
    except Exception as e:
        logging.error(f"Error decoding QR code: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/validate-item-code', methods=['POST'])
@login_required
def validate_item_code_api():
    """Validate item code and return details"""
    try:
        data = request.get_json()
        item_code = data.get('item_code', '').strip()
        
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400
        
        sap = SAPIntegration()
        validation_result = sap.validate_item_code(item_code)
        
        if not validation_result.get('success'):
            return jsonify({
                'success': False,
                'error': validation_result.get('error', 'Item validation failed')
            }), 404
        
        item_description = ''
        try:
            if sap.ensure_logged_in():
                url = f"{sap.base_url}/b1s/v1/Items('{item_code}')"
                response = sap.session.get(url, timeout=10)
                if response.status_code == 200:
                    item_data = response.json()
                    item_description = item_data.get('ItemName', '')
        except Exception as e:
            logging.warning(f"Could not fetch item description: {str(e)}")
        
        item_type = 'none'
        if validation_result.get('batch_required'):
            item_type = 'batch'
        elif validation_result.get('serial_required'):
            item_type = 'serial'
        
        return jsonify({
            'success': True,
            'item_code': item_code,
            'item_description': item_description,
            'item_type': item_type,
            'batch_required': validation_result.get('batch_required', False),
            'serial_required': validation_result.get('serial_required', False),
            'manage_method': validation_result.get('manage_method', 'N')
        })
        
    except Exception as e:
        logging.error(f"Error validating item code: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/submit-direct', methods=['POST'])
@login_required
def submit_direct_transfer():
    """Submit direct inventory transfer to SAP B1 immediately"""
    try:
        data = request.get_json()
        
        required_fields = ['from_warehouse', 'to_warehouse', 'item_code', 'quantity']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        transfer_number = f"DIT/{datetime.now().strftime('%Y%m%d')}/{DirectInventoryTransfer.query.count() + 1:010d}"
        
        transfer = DirectInventoryTransfer(
            transfer_number=transfer_number,
            user_id=current_user.id,
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            from_bin=data.get('from_bin'),
            to_bin=data.get('to_bin'),
            notes=data.get('notes'),
            status='draft'
        )
        
        db.session.add(transfer)
        db.session.flush()
        
        transfer_item = DirectInventoryTransferItem(
            direct_inventory_transfer_id=transfer.id,
            item_code=data.get('item_code'),
            item_description=data.get('item_description'),
            quantity=float(data.get('quantity')),
            item_type=data.get('item_type'),
            from_warehouse_code=data.get('from_warehouse'),
            to_warehouse_code=data.get('to_warehouse'),
            from_bin_code=data.get('from_bin'),
            to_bin_code=data.get('to_bin'),
            batch_number=data.get('batch_number'),
            validation_status='validated'
        )
        
        db.session.add(transfer_item)
        db.session.commit()
        
        sap = SAPIntegration()
        sap_result = sap.create_stock_transfer(
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            items=[{
                'item_code': data.get('item_code'),
                'quantity': float(data.get('quantity')),
                'from_bin': data.get('from_bin'),
                'to_bin': data.get('to_bin'),
                'batch_number': data.get('batch_number'),
                'item_description': data.get('item_description')
            }],
            comments=data.get('notes', f'Direct Transfer {transfer_number}')
        )
        
        if sap_result.get('success'):
            transfer.sap_document_number = str(sap_result.get('doc_num'))
            transfer.status = 'posted'
            db.session.commit()
            
            logging.info(f"✅ Direct transfer posted to SAP: {sap_result.get('doc_num')}")
            
            return jsonify({
                'success': True,
                'transfer_number': transfer_number,
                'sap_doc_number': sap_result.get('doc_num'),
                'message': 'Transfer posted successfully to SAP B1'
            })
        else:
            transfer.status = 'rejected'
            transfer.notes = f"SAP Error: {sap_result.get('error')}"
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': sap_result.get('error', 'Failed to post to SAP B1')
            }), 500
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error submitting direct transfer: {str(e)}")
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@direct_inventory_transfer_bp.route('/api/history', methods=['GET'])
@login_required
def get_transfer_history():
    """Get recent direct inventory transfers for current user"""
    try:
        transfers = DirectInventoryTransfer.query.filter_by(
            user_id=current_user.id
        ).order_by(
            DirectInventoryTransfer.created_at.desc()
        ).limit(20).all()
        
        transfer_list = []
        for transfer in transfers:
            item = transfer.items[0] if transfer.items else None
            
            transfer_list.append({
                'transfer_number': transfer.transfer_number,
                'item_code': item.item_code if item else 'N/A',
                'quantity': item.quantity if item else 0,
                'from_warehouse': transfer.from_warehouse,
                'to_warehouse': transfer.to_warehouse,
                'status': transfer.status,
                'sap_document_number': transfer.sap_document_number,
                'created_at': transfer.created_at.isoformat() if transfer.created_at else None
            })
        
        return jsonify({
            'success': True,
            'transfers': transfer_list
        })
        
    except Exception as e:
        logging.error(f"Error fetching transfer history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
