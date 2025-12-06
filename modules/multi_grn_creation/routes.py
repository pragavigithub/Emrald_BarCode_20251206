"""
Multiple GRN Creation Routes
Multi-step workflow for creating GRNs from multiple Purchase Orders
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import db
from modules.multi_grn_creation.models import MultiGRNBatch, MultiGRNPOLink, MultiGRNLineSelection, MultiGRNBatchDetailsLabel
from modules.multi_grn_creation.services import SAPMultiGRNService
import logging
from datetime import datetime, date
from pathlib import Path
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sap_integration import SAPIntegration

# Use absolute path for template_folder to support PyInstaller .exe builds
multi_grn_bp = Blueprint('multi_grn', __name__, 
                              template_folder=str(Path(__file__).resolve().parent / 'templates'),
                              url_prefix='/multi-grn')


def distribute_quantity_to_packs(total_quantity, num_packs):
    """
    Distribute total quantity across packs as integers.
    First packs get extra units if quantity doesn't divide evenly.
    Uses ROUND_HALF_UP to preserve total quantity (no truncation).
    
    Example: 11 quantity ÷ 3 packs = [4, 4, 3]
    Example: 10 quantity ÷ 3 packs = [4, 3, 3]
    Example: 110.5 quantity ÷ 4 packs = [28, 28, 28, 27] (rounds to 111)
    Example: 110.25 quantity ÷ 4 packs = [28, 28, 27, 27] (rounds to 110)
    
    Args:
        total_quantity: Total quantity to distribute (will be rounded using ROUND_HALF_UP)
        num_packs: Number of packs to distribute into
        
    Returns:
        list: List of integer quantities for each pack
    """
    if num_packs <= 0:
        return []
    
    # Use ROUND_HALF_UP to consistently round .5 up (not banker's rounding)
    total_qty_decimal = Decimal(str(total_quantity))
    total_qty_int = int(total_qty_decimal.to_integral_value(rounding=ROUND_HALF_UP))
    base_qty = total_qty_int // num_packs
    remainder = total_qty_int % num_packs
    
    quantities = []
    for i in range(num_packs):
        if i < remainder:
            quantities.append(base_qty + 1)
        else:
            quantities.append(base_qty)
    
    return quantities

@multi_grn_bp.route('/')
@login_required
def index():
    """Main page - list all GRN batches with filtering, search and pagination"""
    if not current_user.has_permission('multiple_grn'):
        flash('Access denied - Multiple GRN permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search_term = request.args.get('search', '').strip()
        from_date_str = request.args.get('from_date', '').strip()
        to_date_str = request.args.get('to_date', '').strip()
        status_filter = request.args.get('status', '').strip()
        
        query = MultiGRNBatch.query.filter_by(user_id=current_user.id)
        
        if search_term:
            search_pattern = f'%{search_term}%'
            query = query.filter(
                db.or_(
                    MultiGRNBatch.batch_number.ilike(search_pattern),
                    MultiGRNBatch.customer_name.ilike(search_pattern),
                    MultiGRNBatch.customer_code.ilike(search_pattern),
                    MultiGRNBatch.id.cast(db.String).ilike(search_pattern)
                )
            )
        
        if status_filter:
            query = query.filter(MultiGRNBatch.status == status_filter)
        
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
                query = query.filter(MultiGRNBatch.created_at >= from_date)
            except ValueError:
                logging.warning(f"Invalid from_date format: {from_date_str}")
        
        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
                to_date_end = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(MultiGRNBatch.created_at <= to_date_end)
            except ValueError:
                logging.warning(f"Invalid to_date format: {to_date_str}")
        
        query = query.order_by(MultiGRNBatch.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        batches = pagination.items
        
        return render_template('multi_grn/index.html', 
                             batches=batches,
                             per_page=per_page,
                             search_term=search_term,
                             from_date=from_date_str,
                             to_date=to_date_str,
                             status_filter=status_filter,
                             pagination=pagination)
    except Exception as e:
        logging.error(f"Error loading Multi GRN batches: {e}")
        flash('Error loading GRN batches', 'error')
        return redirect(url_for('dashboard'))

@multi_grn_bp.route('/delete/<int:batch_id>', methods=['POST'])
@login_required
def delete_batch(batch_id):
    """Delete a draft batch and all related data"""
    if not current_user.has_permission('multiple_grn'):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        # Verify ownership
        if batch.user_id != current_user.id:
            flash('Access denied - You can only delete your own batches', 'error')
            return redirect(url_for('multi_grn.index'))
        
        # Only allow deleting draft batches
        if batch.status != 'draft':
            flash('Only draft batches can be deleted', 'warning')
            return redirect(url_for('multi_grn.index'))
        
        batch_number = batch.batch_number
        customer_name = batch.customer_name
        
        # Delete the batch (cascade will delete related po_links and line_selections)
        db.session.delete(batch)
        db.session.commit()
        
        logging.info(f"🗑️ Deleted draft batch {batch_number} for customer {customer_name}")
        flash(f'Draft batch {batch_number} has been deleted successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting batch {batch_id}: {e}")
        flash('Error deleting batch. Please try again.', 'error')
    
    return redirect(url_for('multi_grn.index'))

@multi_grn_bp.route('/<int:batch_id>/edit', methods=['GET'])
@login_required
def edit_batch(batch_id):
    """Edit entry point - allows editing draft batches by redirecting to step 2"""
    if not current_user.has_permission('multiple_grn'):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        # Verify ownership
        if batch.user_id != current_user.id:
            flash('Access denied - You can only edit your own batches', 'error')
            return redirect(url_for('multi_grn.index'))
        
        # Only allow editing draft batches
        if batch.status != 'draft':
            flash('Only draft batches can be edited', 'warning')
            return redirect(url_for('multi_grn.index'))
        
        # Set edit mode in session
        session['editing_batch_id'] = batch_id
        
        logging.info(f"✏️ User {current_user.username} editing draft batch {batch.batch_number}")
        flash(f'Editing batch {batch.batch_number} - You can modify PO selection, line items, and QR labels', 'info')
        
        # Redirect to step 2 (PO selection) for editing
        return redirect(url_for('multi_grn.create_step2_select_pos', batch_id=batch_id))
        
    except Exception as e:
        logging.error(f"Error accessing edit for batch {batch_id}: {e}")
        flash('Error accessing batch for editing', 'error')
        return redirect(url_for('multi_grn.index'))

@multi_grn_bp.route('/remove-po/<int:batch_id>/<int:po_link_id>', methods=['POST'])
@login_required
def remove_po_from_batch(batch_id, po_link_id):
    """Remove a PO from the batch (and cascade delete line selections)"""
    if not current_user.has_permission('multiple_grn'):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        # Verify ownership
        if batch.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Only allow removing from draft batches
        if batch.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft batches can be modified'}), 400
        
        po_link = MultiGRNPOLink.query.get_or_404(po_link_id)
        
        # Verify this PO belongs to the batch
        if po_link.batch_id != batch_id:
            return jsonify({'success': False, 'error': 'Invalid PO link'}), 400
        
        # Check if this is the last PO in the batch
        if len(batch.po_links) <= 1:
            return jsonify({'success': False, 'error': 'Cannot remove the last PO. Batch must have at least one Purchase Order.'}), 400
        
        po_doc_num = po_link.po_doc_num
        
        # Delete the PO link (cascade will delete line_selections)
        db.session.delete(po_link)
        batch.total_pos = max(0, batch.total_pos - 1) if batch.total_pos else 0
        db.session.commit()
        
        logging.info(f"🗑️ Removed PO {po_doc_num} from batch {batch_id}")
        return jsonify({'success': True, 'message': f'PO {po_doc_num} removed from batch'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error removing PO {po_link_id} from batch {batch_id}: {e}")
        return jsonify({'success': False, 'error': 'Error removing PO'}), 500

@multi_grn_bp.route('/remove-line/<int:batch_id>/<int:line_id>', methods=['POST'])
@login_required
def remove_line_from_batch(batch_id, line_id):
    """Remove a line selection from the batch (and cascade delete batch/serial details)"""
    if not current_user.has_permission('multiple_grn'):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        # Verify ownership
        if batch.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Only allow removing from draft batches
        if batch.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft batches can be modified'}), 400
        
        line_selection = MultiGRNLineSelection.query.get_or_404(line_id)
        
        # Verify this line belongs to a PO in the batch
        po_link = MultiGRNPOLink.query.get(line_selection.po_link_id)
        if not po_link or po_link.batch_id != batch_id:
            return jsonify({'success': False, 'error': 'Invalid line selection'}), 400
        
        # Check if this is the last line in the batch
        total_lines = sum(len(po.line_selections) for po in batch.po_links)
        if total_lines <= 1:
            return jsonify({'success': False, 'error': 'Cannot remove the last line item. Batch must have at least one line.'}), 400
        
        item_code = line_selection.item_code
        
        # Delete the line selection (cascade will delete batch_details and serial_details)
        db.session.delete(line_selection)
        db.session.commit()
        
        logging.info(f"🗑️ Removed line item {item_code} from batch {batch_id}")
        return jsonify({'success': True, 'message': f'Line item {item_code} removed from batch'})
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error removing line {line_id} from batch {batch_id}: {e}")
        return jsonify({'success': False, 'error': 'Error removing line item'}), 500

@multi_grn_bp.route('/create/step1', methods=['GET', 'POST'])
@login_required
def create_step1_customer():
    """Step 1: Select Document Series and Customer"""
    if not current_user.has_permission('multiple_grn'):
        flash('Access denied', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        series_id = request.form.get('series_id')
        series_name = request.form.get('series_name')
        customer_code = request.form.get('customer_code')
        customer_name = request.form.get('customer_name')
        
        if not customer_code or not customer_name:
            flash('Please select document series and customer', 'error')
            return redirect(url_for('multi_grn.create_step1_customer'))
        
        from datetime import datetime
        batch_number = f"MGRN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        batch = MultiGRNBatch(
            user_id=current_user.id,
            batch_number=batch_number,
            series_id=int(series_id) if series_id else None,
            series_name=series_name,
            customer_code=customer_code,
            customer_name=customer_name,
            status='draft'
        )
        db.session.add(batch)
        db.session.commit()
        
        logging.info(f"✅ Created GRN batch {batch.batch_number} for series {series_name}, customer {customer_name}")
        return redirect(url_for('multi_grn.create_step2_select_pos', batch_id=batch.id))
    
    return render_template('multi_grn/step1_customer.html')

@multi_grn_bp.route('/create/step2/<int:batch_id>', methods=['GET', 'POST'])
@login_required
def create_step2_select_pos(batch_id):
    """Step 2: Select Purchase Orders"""
    batch = MultiGRNBatch.query.get_or_404(batch_id)
    
    if batch.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('multi_grn.index'))
    
    if request.method == 'POST':
        selected_pos = request.form.getlist('selected_pos[]')
        
        if not selected_pos:
            flash('Please select at least one Purchase Order', 'error')
            return redirect(url_for('multi_grn.create_step2_select_pos', batch_id=batch_id))
        
        # Get existing PO entries in this batch to avoid duplicates
        existing_po_entries = {po_link.po_doc_entry for po_link in batch.po_links}
        
        added_count = 0
        skipped_count = 0
        
        for po_data_json in selected_pos:
            po_data = json.loads(po_data_json)
            po_doc_entry = po_data['DocEntry']
            
            # Check if this PO is already in the batch
            if po_doc_entry in existing_po_entries:
                logging.warning(f"⚠️ PO {po_data['DocNum']} (DocEntry={po_doc_entry}) already exists in batch {batch_id}, skipping")
                skipped_count += 1
                continue
            
            po_link = MultiGRNPOLink(
                batch_id=batch.id,
                po_doc_entry=po_doc_entry,
                po_doc_num=po_data['DocNum'],
                po_card_code=po_data['CardCode'],
                po_card_name=po_data['CardName'],
                po_doc_date=datetime.strptime(po_data['DocDate'][:10], '%Y-%m-%d').date() if po_data.get('DocDate') else None,
                po_doc_total=Decimal(str(po_data.get('DocTotal', 0))),
                status='selected'
            )
            db.session.add(po_link)
            existing_po_entries.add(po_doc_entry)
            added_count += 1
        
        if added_count > 0:
            batch.total_pos = len(batch.po_links) + added_count
            db.session.commit()
            logging.info(f"✅ Added {added_count} new POs to batch {batch_id}")
            
            if skipped_count > 0:
                flash(f'Added {added_count} Purchase Orders. Skipped {skipped_count} duplicate(s).', 'success')
            else:
                flash(f'Selected {added_count} Purchase Orders', 'success')
        else:
            if skipped_count > 0:
                flash(f'All {skipped_count} selected PO(s) are already in this batch', 'warning')
            else:
                flash('No Purchase Orders were added', 'warning')
        
        return redirect(url_for('multi_grn.create_step3_select_lines', batch_id=batch_id))
    
    sap_service = SAPMultiGRNService()
    
    # Use series-based filtering if series_id is available
    if batch.series_id:
        result = sap_service.fetch_purchase_orders_by_series_and_card(batch.series_id, batch.customer_code)
        logging.info(f"📊 Fetching POs with Series filter: Series={batch.series_id}, CardCode={batch.customer_code}")
    else:
        # Fallback to legacy method without series filtering
        result = sap_service.fetch_open_purchase_orders_by_name(batch.customer_name)
        logging.info(f"📊 Fetching POs without Series filter: CardName={batch.customer_name}")
    
    if not result['success']:
        flash(f"Error fetching Purchase Orders: {result.get('error')}", 'error')
        return redirect(url_for('multi_grn.index'))
    
    purchase_orders = result.get('purchase_orders', [])
    logging.info(f"📊 Found {len(purchase_orders)} open POs for customer {batch.customer_name} ({batch.customer_code})")
    return render_template('multi_grn/step2_select_pos.html', batch=batch, purchase_orders=purchase_orders)

@multi_grn_bp.route('/create/step3/<int:batch_id>', methods=['GET', 'POST'])
@login_required
def create_step3_select_lines(batch_id):
    """Step 3: Select line items from POs and manage item details"""
    batch = MultiGRNBatch.query.get_or_404(batch_id)
    
    if batch.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('multi_grn.index'))
    
    if request.method == 'POST':
        # Process line selection from Step 2 (initial selection)
        sap_service = SAPMultiGRNService()
        
        for po_link in batch.po_links:
            selected_lines = request.form.getlist(f'lines_po_{po_link.id}[]')
            
            for line_data_json in selected_lines:
                line_data = json.loads(line_data_json)
                qty_key = f'qty_po_{po_link.id}_line_{line_data["LineNum"]}'
                
                # Sanitize open_qty from SAP - ensure it's a valid number
                raw_open_qty = line_data.get('OpenQuantity', line_data.get('Quantity', 0))
                try:
                    open_qty = Decimal(str(raw_open_qty)) if raw_open_qty not in (None, '', 'None') else Decimal('0')
                except (ValueError, InvalidOperation):
                    open_qty = Decimal('0')
                
                # Handle empty receive quantity field - use open quantity as default
                receive_qty_str = request.form.get(qty_key, '').strip()
                if receive_qty_str == '' or receive_qty_str is None:
                    selected_qty = open_qty
                else:
                    try:
                        selected_qty = Decimal(receive_qty_str)
                    except (ValueError, InvalidOperation):
                        # If invalid input, default to open quantity
                        logging.warning(f"Invalid receive quantity '{receive_qty_str}' for item {line_data.get('ItemCode')}, using open qty {open_qty}")
                        selected_qty = open_qty
                
                if selected_qty > 0:
                    # Check if line already exists to prevent duplicates
                    existing_line = MultiGRNLineSelection.query.filter_by(
                        po_link_id=po_link.id,
                        po_line_num=line_data['LineNum'],
                        item_code=line_data['ItemCode']
                    ).first()
                    
                    if not existing_line:
                        # CRITICAL FIX: Validate item with SAP to get correct batch/serial/management flags
                        item_code = line_data['ItemCode']
                        validation_result = sap_service.validate_item_code(item_code)
                        
                        # Extract validation data or use safe defaults
                        if validation_result.get('success'):
                            batch_required = 'Y' if validation_result.get('batch_managed', False) else 'N'
                            serial_required = 'Y' if validation_result.get('serial_managed', False) else 'N'
                            manage_method = validation_result.get('management_method', 'A')
                            inventory_type = validation_result.get('inventory_type', 'standard')
                        else:
                            # Validation failed - use safe defaults (standard item)
                            logging.warning(f"⚠️ SAP validation failed for {item_code}: {validation_result.get('error')}")
                            batch_required = 'N'
                            serial_required = 'N'
                            manage_method = 'A'
                            inventory_type = 'standard'
                        
                        line_selection = MultiGRNLineSelection(
                            po_link_id=po_link.id,
                            po_line_num=line_data['LineNum'],
                            item_code=item_code,
                            item_description=line_data.get('ItemDescription', ''),
                            ordered_quantity=Decimal(str(line_data.get('Quantity', 0))),
                            open_quantity=Decimal(str(line_data.get('OpenQuantity', line_data.get('Quantity', 0)))),
                            selected_quantity=selected_qty,
                            warehouse_code=line_data.get('WarehouseCode', ''),
                            unit_price=Decimal(str(line_data.get('UnitPrice', 0))),
                            line_status=line_data.get('LineStatus', ''),
                            inventory_type=inventory_type,
                            batch_required=batch_required,
                            serial_required=serial_required,
                            manage_method=manage_method
                        )
                        db.session.add(line_selection)
                    else:
                        # Update existing line with new quantity
                        existing_line.selected_quantity = selected_qty
        
        db.session.commit()
        logging.info(f"✅ Line items selected for batch {batch_id}")
        flash('Line items selected successfully', 'success')
        # Stay on Step 3 to allow detail entry
        return redirect(url_for('multi_grn.create_step3_select_lines', batch_id=batch_id))
    
    # GET request - check if lines already exist
    has_lines = any(po_link.line_selections for po_link in batch.po_links)
    
    if has_lines:
        # Lines already selected, show detail entry view
        return render_template('multi_grn/step3_detail.html', batch=batch)
    else:
        # No lines selected yet, show line selection view
        sap_service = SAPMultiGRNService()
        po_details = []
        
        for po_link in batch.po_links:
            result = sap_service.fetch_open_purchase_orders_by_name(batch.customer_name)
            logging.info(f"📊 Step 3 - Fetched PO details for {batch.customer_name}: Success={result.get('success')}")
            
            # Handle both success/failure cases safely
            if result.get('success'):
                for po in result.get('purchase_orders', []):
                    if po['DocEntry'] == po_link.po_doc_entry:
                        po_details.append({
                            'po_link': po_link,
                            'lines': po.get('OpenLines', [])
                        })
                        break
            else:
                # SAP login failed - show error to user
                error_msg = result.get('error', 'Failed to fetch Purchase Order details from SAP')
                logging.error(f"❌ Step 3 error for batch {batch_id}: {error_msg}")
                flash(f'Error loading PO details: {error_msg}', 'error')
                return redirect(url_for('multi_grn.index'))
        
        return render_template('multi_grn/step3_select_lines.html', batch=batch, po_details=po_details)

@multi_grn_bp.route('/create/step4/<int:batch_id>')
@login_required
def create_step4_review(batch_id):
    """Step 4: Review selections before posting"""
    batch = MultiGRNBatch.query.get_or_404(batch_id)
    
    if batch.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('multi_grn.index'))
    
    return render_template('multi_grn/step4_review.html', batch=batch)

@multi_grn_bp.route('/create/step5/<int:batch_id>', methods=['POST'])
@login_required
def create_step5_post(batch_id):
    """Step 5: Submit batch for QC approval (NO SAP posting here - posting happens after QC approval)"""
    batch = MultiGRNBatch.query.get_or_404(batch_id)
    
    if batch.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        if batch.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft batches can be submitted'}), 400
        
        if not batch.po_links:
            return jsonify({'success': False, 'error': 'Cannot submit batch without purchase orders'}), 400
        
        has_lines = any(po_link.line_selections for po_link in batch.po_links)
        if not has_lines:
            return jsonify({'success': False, 'error': 'Cannot submit batch without line items'}), 400
        
        batch.status = 'submitted'
        batch.submitted_at = datetime.utcnow()
        db.session.commit()
        
        logging.info(f"📤 Multi GRN batch {batch_id} submitted for QC approval by {current_user.username}")
        return jsonify({
            'success': True,
            'message': 'Batch submitted for QC approval. SAP posting will occur after QC approves.',
            'status': 'submitted',
            'redirect_url': url_for('multi_grn.index')
        })
        
    except Exception as e:
        logging.error(f"Error submitting Multi GRN batch: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/batch/<int:batch_id>')
@login_required
def view_batch(batch_id):
    """View batch details with eagerly loaded relationships for QR label generation"""
    from sqlalchemy.orm import joinedload
    
    # Eagerly load all relationships needed for the view
    batch = MultiGRNBatch.query.options(
        joinedload(MultiGRNBatch.po_links).joinedload(MultiGRNPOLink.line_selections).joinedload(MultiGRNLineSelection.batch_details),
        joinedload(MultiGRNBatch.po_links).joinedload(MultiGRNPOLink.line_selections).joinedload(MultiGRNLineSelection.serial_details)
    ).get_or_404(batch_id)
    
    if batch.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('multi_grn.index'))
    
    logging.info(f"📋 Viewing batch {batch_id}: {len(batch.po_links)} POs")
    for po_link in batch.po_links:
        for line in po_link.line_selections:
            logging.debug(f"   Line {line.id}: {line.item_code}, batch_details={len(line.batch_details)}, serial_details={len(line.serial_details)}")
    
    return render_template('multi_grn/view_batch.html', batch=batch)

@multi_grn_bp.route('/batch/<int:batch_id>/submit', methods=['POST'])
@login_required
def submit_batch(batch_id):
    """Submit Multi GRN batch for QC approval"""
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        if batch.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if batch.status != 'draft':
            return jsonify({'success': False, 'error': 'Only draft batches can be submitted'}), 400
        
        if not batch.po_links:
            return jsonify({'success': False, 'error': 'Cannot submit batch without purchase orders'}), 400
        
        has_lines = any(po_link.line_selections for po_link in batch.po_links)
        if not has_lines:
            return jsonify({'success': False, 'error': 'Cannot submit batch without line items'}), 400
        
        batch.status = 'submitted'
        batch.submitted_at = datetime.utcnow()
        db.session.commit()
        
        logging.info(f"📤 Multi GRN batch {batch_id} submitted for QC approval by {current_user.username}")
        return jsonify({
            'success': True,
            'message': 'Batch submitted for QC approval',
            'status': 'submitted'
        })
        
    except Exception as e:
        logging.error(f"Error submitting Multi GRN batch: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/batch/<int:batch_id>/approve', methods=['POST'])
@login_required
def approve_batch(batch_id):
    """QC approve Multi GRN batch and post consolidated GRN to SAP B1"""
    from datetime import datetime
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if batch.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted batches can be approved'}), 400
        
        from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails
        
        total_items = 0
        verified_items = 0
        
        for po_link in batch.po_links:
            for line in po_link.line_selections:
                batch_details = MultiGRNBatchDetails.query.filter_by(line_selection_id=line.id).all()
                serial_details = MultiGRNSerialDetails.query.filter_by(line_selection_id=line.id).all()
                
                for detail in batch_details:
                    total_items += 1
                    if detail.status == 'verified':
                        verified_items += 1
                
                for detail in serial_details:
                    total_items += 1
                    if detail.status == 'verified':
                        verified_items += 1
        
        if total_items > 0 and verified_items != total_items:
            return jsonify({
                'success': False, 
                'error': f'Not all items have been verified. {verified_items}/{total_items} items verified. Please scan all QR codes before approval.'
            }), 400
        
        qc_notes = ''
        if request.form:
            qc_notes = request.form.get('qc_notes', '')
        elif request.json:
            qc_notes = request.json.get('qc_notes', '')
        
        batch.status = 'qc_approved'
        batch.qc_approver_id = current_user.id
        batch.qc_approved_at = datetime.utcnow()
        batch.qc_notes = qc_notes
        db.session.commit()
        
        sap_service = SAPMultiGRNService()
        
        if not batch.po_links:
            return jsonify({'success': False, 'error': 'No purchase orders in this batch'}), 400
        
        first_po_link = batch.po_links[0]
        card_code = first_po_link.po_card_code
        
        for po_link in batch.po_links:
            if po_link.po_card_code != card_code:
                error_msg = f'Cannot consolidate POs with different vendors. Found {card_code} and {po_link.po_card_code}. All POs must be from the same vendor.'
                logging.error(f"❌ {error_msg}")
                batch.status = 'failed'
                batch.error_log = error_msg
                db.session.commit()
                return jsonify({'success': False, 'error': error_msg}), 400
        
        consolidated_document_lines = []
        line_number = 0
        all_line_selections = []
        
        for po_link in batch.po_links:
            if not po_link.line_selections:
                continue
            
            for line in po_link.line_selections:
                all_line_selections.append({
                    'line': line,
                    'po_link': po_link
                })
        
        for item in all_line_selections:
            line = item['line']
            po_link = item['po_link']
            
            if line.line_status == 'manual' or line.po_line_num == -1:
                doc_line = {
                    'LineNum': line_number,
                    'ItemCode': line.item_code,
                    'Quantity': float(line.selected_quantity),
                    'WarehouseCode': line.warehouse_code
                }
            else:
                doc_line = {
                    'LineNum': line_number,
                    'BaseType': 22,
                    'BaseEntry': po_link.po_doc_entry,
                    'BaseLine': line.po_line_num,
                    'ItemCode': line.item_code,
                    'Quantity': float(line.selected_quantity),
                    'WarehouseCode': line.warehouse_code
                }
            
            if line.bin_location:
                try:
                    bin_abs_entry = int(line.bin_location)
                    logging.info(f"✅ Using numeric BinAbsEntry: {bin_abs_entry}")
                except (ValueError, TypeError):
                    bin_result = sap_service.get_bin_abs_entry(line.bin_location)
                    if bin_result.get('success'):
                        bin_abs_entry = bin_result.get('abs_entry')
                        logging.info(f"✅ Fetched BinAbsEntry {bin_abs_entry} for BinCode {line.bin_location}")
                    else:
                        logging.warning(f"⚠️ Failed to fetch BinAbsEntry for {line.bin_location}: {bin_result.get('error')}")
                        bin_abs_entry = None
                
                if bin_abs_entry:
                    doc_line['DocumentLinesBinAllocations'] = [{
                        'BinAbsEntry': bin_abs_entry,
                        'Quantity': float(line.selected_quantity),
                        'SerialAndBatchNumbersBaseLine': 0
                    }]

            def safe_isoformat(value):
                if isinstance(value, datetime):
                    return value.isoformat()
                return value
            if line.batch_details and (line.batch_required == 'Y' or line.manage_method == 'R'):
                batch_numbers = []
                for batch_detail in line.batch_details:
                    batch_entry = {
                        'BatchNumber': batch_detail.batch_number,
                        'Quantity': float(batch_detail.quantity)
                    }
                    if batch_detail.expiry_date:
                        batch_entry['ExpiryDate'] = batch_detail.expiry_date
                    if batch_detail.manufacturer_serial_number:
                        batch_entry['ManufacturerSerialNumber'] = batch_detail.manufacturer_serial_number
                    if batch_detail.internal_serial_number:
                        batch_entry['InternalSerialNumber'] = batch_detail.internal_serial_number
                    batch_numbers.append(batch_entry)
                
                if batch_numbers:
                    doc_line['BatchNumbers'] = batch_numbers
            
            elif line.serial_details and line.serial_required == 'Y':
                serial_numbers = []
                for serial_detail in line.serial_details:
                    serial_entry = {
                        'InternalSerialNumber': serial_detail.serial_number,
                        'Quantity': 1.0
                    }
                    if serial_detail.manufacturer_serial_number:
                        serial_entry['ManufacturerSerialNumber'] = serial_detail.manufacturer_serial_number
                    if serial_detail.expiry_date:
                        serial_entry['ExpiryDate'] = serial_detail.expiry_date.isoformat()
                    serial_numbers.append(serial_entry)
                
                if serial_numbers:
                    doc_line['SerialNumbers'] = serial_numbers
            
            elif line.serial_numbers and line.serial_required == 'Y':
                serial_data = json.loads(line.serial_numbers) if isinstance(line.serial_numbers, str) else line.serial_numbers
                doc_line['SerialNumbers'] = serial_data
            
            elif line.batch_numbers and (line.batch_required == 'Y' or line.manage_method == 'R'):
                batch_data = json.loads(line.batch_numbers) if isinstance(line.batch_numbers, str) else line.batch_numbers
                doc_line['BatchNumbers'] = batch_data
            
            consolidated_document_lines.append(doc_line)
            line_number += 1
        
        if not consolidated_document_lines:
            error_msg = 'No line items selected for posting. Please select at least one item from the purchase orders.'
            logging.error(f"❌ {error_msg}")
            batch.status = 'failed'
            batch.error_log = error_msg
            db.session.commit()
            return jsonify({'success': False, 'error': error_msg}), 400
        
        po_nums = ', '.join([po_link.po_doc_num for po_link in batch.po_links])

          # already a string

        datevalue = safe_isoformat(date.today().isoformat())
        print("datevaluedatevalue----->",datevalue)
        grn_data = {
            'CardCode': card_code,
            'DocDate': datevalue,
            'DocDueDate': datevalue,
            'Comments': f'QC Approved - Batch {batch.batch_number}. POs: {po_nums}',
            'NumAtCard': f'{batch.batch_number}',
            'BPL_IDAssignedToInvoice': 5,
            'DocumentLines': consolidated_document_lines
        }
        
        logging.info(f"📦 Consolidated GRN payload: {len(consolidated_document_lines)} lines from {len(batch.po_links)} POs")
        logging.debug(f"   GRN JSON: {json.dumps(grn_data, indent=2)}")
        print(grn_data)
        result = sap_service.create_purchase_delivery_note(grn_data)
        
        if result['success']:
            grn_doc_num = result.get('doc_num')
            grn_doc_entry = result.get('doc_entry')
            
            for po_link in batch.po_links:
                po_link.status = 'posted'
                po_link.sap_grn_doc_num = grn_doc_num
                po_link.sap_grn_doc_entry = grn_doc_entry
                po_link.posted_at = datetime.utcnow()
            
            batch.status = 'posted'
            batch.total_grns_created = 1
            batch.completed_at = datetime.utcnow()
            batch.posted_at = datetime.utcnow()
            db.session.commit()
            
            logging.info(f"✅ Batch {batch.batch_number} QC approved and posted: 1 consolidated GRN created (DocNum={grn_doc_num})")
            return jsonify({
                'success': True,
                'grn_doc_num': grn_doc_num,
                'grn_doc_entry': grn_doc_entry,
                'po_count': len(batch.po_links),
                'line_count': len(consolidated_document_lines),
                'message': f'Batch approved by QC and successfully posted to SAP B1. GRN #{grn_doc_num} created with {len(consolidated_document_lines)} lines from {len(batch.po_links)} purchase orders.'
            })
        else:
            error_msg = result.get('error', 'Unknown error')
            for po_link in batch.po_links:
                po_link.status = 'failed'
                po_link.error_message = error_msg
            
            batch.status = 'failed'
            batch.error_log = error_msg
            db.session.commit()
            
            logging.error(f"❌ Failed to create consolidated GRN for batch {batch.batch_number}: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
        
    except Exception as e:
        logging.error(f"❌ Error approving Multi GRN batch {batch_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/batch/<int:batch_id>/reject', methods=['POST'])
@login_required
def reject_batch(batch_id):
    """QC reject Multi GRN batch"""
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            return jsonify({'success': False, 'error': 'QC permissions required'}), 403
        
        if batch.status != 'submitted':
            return jsonify({'success': False, 'error': 'Only submitted batches can be rejected'}), 400
        
        qc_notes = ''
        if request.form:
            qc_notes = request.form.get('qc_notes', '')
        elif request.json:
            qc_notes = request.json.get('qc_notes', '')
        
        if not qc_notes:
            return jsonify({'success': False, 'error': 'Rejection reason is required'}), 400
        
        batch.status = 'rejected'
        batch.qc_approver_id = current_user.id
        batch.qc_approved_at = datetime.utcnow()
        batch.qc_notes = qc_notes
        
        db.session.commit()
        
        logging.info(f"❌ Multi GRN batch {batch_id} rejected by {current_user.username}")
        return jsonify({'success': True, 'message': 'Batch rejected by QC'})
        
    except Exception as e:
        logging.error(f"Error rejecting Multi GRN batch: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/batch/<int:batch_id>/qc-review')
@login_required
def qc_review_batch(batch_id):
    """QC Review page for line-by-line verification"""
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)

        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            flash('Access denied - QC permissions required', 'error')
            return redirect(url_for('dashboard'))

        if batch.status not in ['submitted', 'qc_approved','posted']:
            flash('Only submitted batches can be reviewed', 'error')
            return redirect(url_for('qc_dashboard'))

        from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails

        total_line_items = 0
        verified_line_items = 0
        all_verified = False

        for po_link in batch.po_links:
            for line in po_link.line_selections:
                batch_details_count = MultiGRNBatchDetails.query.filter_by(line_selection_id=line.id).count()
                serial_details_count = MultiGRNSerialDetails.query.filter_by(line_selection_id=line.id).count()
                total_line_items += batch_details_count + serial_details_count
                verified_batch = MultiGRNBatchDetails.query.filter_by(
                    line_selection_id=line.id,
                    status='verified'
                ).count()
                verified_serial = MultiGRNSerialDetails.query.filter_by(
                    line_selection_id=line.id,
                    status='verified'
                ).count()

                verified_line_items += verified_batch + verified_serial

        all_verified = total_line_items > 0 and verified_line_items == total_line_items

        return render_template('multi_grn/qc_review.html',
                             batch=batch,
                             total_line_items=total_line_items,
                             verified_line_items=verified_line_items,
                             all_verified=all_verified)
    except Exception as e:
        logging.error(f"Error loading QC review page: {str(e)}")
        flash('Error loading QC review page', 'error')
        return redirect(url_for('qc_dashboard'))
# @multi_grn_bp.route('/batch/<int:batch_id>/qc-reviews')
# @login_required
# def qc_review_batchs(batch_id):
#     """QC Review page for line-by-line verification or JSON API"""
#     try:
#         batch = MultiGRNBatch.query.get_or_404(batch_id)
#
#         # Permission check
#         if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
#             return _return_error("Access denied - QC permissions required", 403)
#
#         # Status check
#         if batch.status not in ['submitted', 'qc_approved']:
#             return _return_error("Only submitted batches can be reviewed")
#
#         # Import models
#         from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails
#
#         total_line_items = 0
#         verified_line_items = 0
#
#         # Count line items
#         for po_link in batch.po_links:
#             for line in po_link.line_selections:
#                 batch_count = MultiGRNBatchDetails.query.filter_by(line_selection_id=line.id).count()
#                 serial_count = MultiGRNSerialDetails.query.filter_by(line_selection_id=line.id).count()
#
#                 verified_batch = MultiGRNBatchDetails.query.filter_by(
#                     line_selection_id=line.id,
#                     status='verified'
#                 ).count()
#
#                 verified_serial = MultiGRNSerialDetails.query.filter_by(
#                     line_selection_id=line.id,
#                     status='verified'
#                 ).count()
#
#                 total_line_items += batch_count + serial_count
#                 verified_line_items += verified_batch + verified_serial
#
#         all_verified = (total_line_items > 0 and verified_line_items == total_line_items)
#
#         # ----------------------------------------
#         # 🔥 RETURN JSON WHEN API REQUEST
#         # ----------------------------------------
#         if request.accept_mimetypes['application/json']:
#             return jsonify({
#                 "success": True,
#                 "batch": {
#                     "id": batch.id,
#                     "batch_number": batch.batch_number,
#                     "customer_name": batch.customer_name,
#                     "customer_code": batch.customer_code,
#                     "created_by": batch.user.username,
#                     "created_at": str(batch.created_at),  # safe for JSON
#                     "status": batch.status,
#                     "total_pos": batch.total_pos,
#                 },
#                 "total_line_items": total_line_items,
#                 "verified_line_items": verified_line_items,
#                 "all_verified": all_verified
#             })
#
#         # ----------------------------------------
#         # 🔥 OTHERWISE RETURN HTML TEMPLATE AS USUAL
#         # ----------------------------------------
#         return render_template(
#             'multi_grn/qc_review.html',
#             batch=batch,
#             total_line_items=total_line_items,
#             verified_line_items=verified_line_items,
#             all_verified=all_verified
#         )
#
#     except Exception as e:
#         logging.error(f"Error loading QC review page: {str(e)}")
#         return _return_error("Error loading QC review page")
#
#
# # Helper to return JSON on error
# def _return_error(msg, code=400):
#     if request.accept_mimetypes['application/json']:
#         return jsonify({"success": False, "error": msg}), code
#     flash(msg, "error")
#     return redirect(url_for('qc_dashboard'))
from flask import request, jsonify


@multi_grn_bp.route('/batch/<int:batch_id>/qc-reviews')
@login_required
def qc_review_batchs(batch_id):
    """QC Review page for line-by-line verification OR JSON API response"""
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)

        # --- Permission check ---
        if not current_user.has_permission('qc_dashboard') and current_user.role not in ['admin', 'manager']:
            msg = 'Access denied - QC permissions required'
            # If API request => JSON error, else redirect with flash
            if _wants_json():
                return jsonify({"success": False, "error": msg}), 403
            flash(msg, 'error')
            return redirect(url_for('dashboard'))

        # --- Status check ---
        if batch.status not in ['submitted', 'qc_approved','posted']:
            msg = 'Only submitted batches can be reviewed'
            if _wants_json():
                return jsonify({"success": False, "error": msg}), 400
            flash(msg, 'error')
            return redirect(url_for('qc_dashboard'))

        from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails

        total_line_items = 0
        verified_line_items = 0

        # ---- Count totals & verified from Details tables ----
        for po_link in batch.po_links:
            for line in po_link.line_selections:
                batch_details_count = MultiGRNBatchDetails.query.filter_by(
                    line_selection_id=line.id
                ).count()
                serial_details_count = MultiGRNSerialDetails.query.filter_by(
                    line_selection_id=line.id
                ).count()

                total_line_items += batch_details_count + serial_details_count

                verified_batch = MultiGRNBatchDetails.query.filter_by(
                    line_selection_id=line.id,
                    status='verified'
                ).count()
                verified_serial = MultiGRNSerialDetails.query.filter_by(
                    line_selection_id=line.id,
                    status='verified'
                ).count()

                verified_line_items += verified_batch + verified_serial

        all_verified = total_line_items > 0 and verified_line_items == total_line_items

        # =====================================================================
        # 🔥 JSON API RESPONSE (for mobile/React/Flutter)
        # Triggered when:
        #   - Accept: application/json   OR
        #   - Content-Type: application/json (like you mentioned)
        # =====================================================================
        if _wants_json():
            po_links_json = []
            # ------------------------------
            # If NO PO LINKS → return empty response
            # ------------------------------
            if not batch.po_links or len(batch.po_links) == 0:
                batch_header = {
                    "id": batch.id,
                    "batch_number": batch.batch_number,
                    "customer_code": batch.customer_code,
                    "customer_name": batch.customer_name,
                    "status": batch.status,
                    "total_pos": 0,
                    "total_grns_created": batch.total_grns_created,
                    "created_at": batch.created_at.isoformat() if batch.created_at else None,
                    "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
                    "posted_at": batch.posted_at.isoformat() if batch.posted_at else None,
                    "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                }

                return jsonify({
                    "success": True,
                    "batch": batch_header,
                    "stats": {
                        "total_line_items": 0,
                        "verified_line_items": 0,
                        "all_verified": False,
                        "percentage": 0,
                    },
                    "po_links": [],
                    "message": "GRN line items not generated for this batch."
                })
            for po_link in batch.po_links:

                lines_json = []
                for line in po_link.line_selections:
                    # Batch details for this line
                    batch_details_json = []
                    for d in getattr(line, 'batch_details', []):
                        batch_details_json.append({
                            "id": d.id,
                            "line_selection_id": d.line_selection_id,
                            "batch_number": d.batch_number,
                            "quantity": float(d.quantity or 0),
                            "manufacturer_serial_number": d.manufacturer_serial_number,
                            "internal_serial_number": d.internal_serial_number,
                            "expiry_date": d.expiry_date,  # string as stored
                            "barcode": d.barcode,
                            "grn_number": d.grn_number,
                            "qty_per_pack": float(d.qty_per_pack or 0) if d.qty_per_pack is not None else None,
                            "no_of_packs": d.no_of_packs,
                            "status": d.status,
                            "created_at": d.created_at.isoformat() if d.created_at else None,
                        })

                    # Serial details (if your model has similar fields)
                    serial_details_json = []
                    for s in getattr(line, 'serial_details', []):
                        serial_details_json.append({
                            "id": s.id,
                            "line_selection_id": s.line_selection_id,
                            "serial_number": getattr(s, 'serial_number', None),
                            "expiry_date": s.expiry_date.isoformat() if getattr(s, 'expiry_date', None) else None,
                            "status": s.status,
                            "grn_number": getattr(s, 'grn_number', None),
                            "created_at": s.created_at.isoformat() if getattr(s, 'created_at', None) else None,
                        })

                    lines_json.append({
                        "id": line.id,
                        "item_code": line.item_code,
                        "item_description": line.item_description,
                        "selected_quantity": float(getattr(line, 'selected_quantity', 0) or 0),
                        "uom_code": getattr(line, 'uom_code', None),
                        "warehouse_code": getattr(line, 'warehouse_code', None),
                        "batch_details": batch_details_json,
                        "serial_details": serial_details_json,
                    })

                po_links_json.append({
                    "id": po_link.id,
                    "po_doc_entry": getattr(po_link, 'po_doc_entry', None),
                    "po_doc_num": getattr(po_link, 'po_doc_num', None),
                    "po_card_code": getattr(po_link, 'po_card_code', None),
                    "po_card_name": getattr(po_link, 'po_card_name', None),
                    "line_selections": lines_json,
                })

            batch_header = {
                "id": batch.id,
                "batch_number": batch.batch_number,
                "user_id": batch.user_id,
                "series_id": batch.series_id,
                "series_name": batch.series_name,
                "customer_code": batch.customer_code,
                "customer_name": batch.customer_name,
                "status": batch.status,
                "total_pos": batch.total_pos,
                "total_grns_created": batch.total_grns_created,
                "sap_session_metadata": batch.sap_session_metadata,
                "error_log": batch.error_log,
                "created_at": batch.created_at.isoformat() if batch.created_at else None,
                "posted_at": batch.posted_at.isoformat() if batch.posted_at else None,
                "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
                "qc_approver_id": batch.qc_approver_id,
                "qc_approved_at": batch.qc_approved_at.isoformat() if batch.qc_approved_at else None,
                "qc_notes": batch.qc_notes,
                "created_by_username": batch.user.username if batch.user else None,
                "qc_approver_username": batch.qc_approver.username if batch.qc_approver else None,
            }

            return jsonify({
                "success": True,
                "batch": batch_header,
                "stats": {
                    "total_line_items": total_line_items,
                    "verified_line_items": verified_line_items,
                    "all_verified": all_verified,
                    "percentage": (verified_line_items / total_line_items * 100) if total_line_items > 0 else 0,
                },
                "po_links": po_links_json,
            })

        # =====================================================================
        # 🌐 NORMAL HTML RESPONSE (template unchanged)
        # =====================================================================
        return render_template(
            'multi_grn/qc_review.html',
            batch=batch,
            total_line_items=total_line_items,
            verified_line_items=verified_line_items,
            all_verified=all_verified
        )

    except Exception as e:
        logging.error(f"Error loading QC review page: {str(e)}")
        if _wants_json():
            return jsonify({"success": False, "error": str(e)}), 500
        flash('Error loading QC review page', 'error')
        return redirect(url_for('qc_dashboard'))


def _wants_json():
    """
    Detect if client expects JSON.
    You said you send header Content-Type: application/json,
    so we also check that (even though it's non-standard for GET).
    """
    ct = (request.headers.get('Content-Type') or '').lower()
    accept = (request.headers.get('Accept') or '').lower()
    return (
            'application/json' in accept
            or 'application/json' in ct
            or request.args.get('format') == 'json'
    )


@multi_grn_bp.route('/api/scan-qr-code', methods=['POST'])
@login_required
def scan_qr_code():
    """
    Scan QR code, validate pack, update child & parent status.
    
    LOGIC:
    1. Scan QR code → Get pack GRN (e.g., MGN-19-43-1-1)
    2. Find child record in multi_grn_batch_details_label table
    3. Mark child status = 'verified'
    4. Check if ALL children for the same parent (batch_detail_id) are verified
    5. If ALL verified → Update parent (multi_grn_batch_details) status = 'verified'
    
    Example:
    - Parent: multi_grn_batch_details (id=1, grn_number=MGN-19-43-1, status=pending)
    - Children: multi_grn_batch_details_label
        - id=1, batch_detail_id=1, grn_number=MGN-19-43-1-1, status=verified
        - id=2, batch_detail_id=1, grn_number=MGN-19-43-1-2, status=pending
        - id=3, batch_detail_id=1, grn_number=MGN-19-43-1-3, status=pending
    - When all 3 children are verified → Parent status becomes 'verified'
    """
    try:
        # ---------------------------
        # 1. Read Request
        # ---------------------------
        data = request.get_json()
        qr_data = data.get('qr_data', '')

        if not qr_data:
            return jsonify({'success': False, 'error': 'QR code data is required'}), 400

        # ---------------------------
        # 2. Decode QR JSON
        # ---------------------------
        try:
            qr_json = json.loads(qr_data)
            grn_id = qr_json.get('id', '')        # e.g. MGN-19-43-1-1 (child/pack GRN)
            qr_qty = int(qr_json.get('qty', 0))   # quantity from QR label
        except Exception:
            return jsonify({'success': False, 'error': 'Invalid QR code format'}), 400

        if not grn_id:
            return jsonify({'success': False, 'error': 'QR code ID missing'}), 400

        logging.info(f"🔍 QR scan received: GRN={grn_id}, Qty={qr_qty}")

        from modules.multi_grn_creation.models import (
            MultiGRNBatchDetails,
            MultiGRNBatchDetailsLabel
        )

        # ---------------------------
        # 3. Find Child Record (pack label) by GRN number
        # ---------------------------
        # The scanned QR contains the full pack GRN (e.g., MGN-19-43-1-1)
        child_record = MultiGRNBatchDetailsLabel.query.filter_by(grn_number=grn_id).first()

        if not child_record:
            # Try with parsed GRN if direct match fails
            parts = grn_id.split("-")
            if len(parts) >= 5:
                pack_grn = "-".join(parts[:5])
                child_record = MultiGRNBatchDetailsLabel.query.filter_by(grn_number=pack_grn).first()
        
        if not child_record:
            logging.error(f"❌ Pack not found: GRN={grn_id}")
            return jsonify({
                'success': False,
                'error': f'Pack {grn_id} not found in database. Please ensure you are scanning the correct QR label.'
            }), 404

        # ---------------------------
        # 4. Get Parent Record using batch_detail_id relationship
        # ---------------------------
        parent_record = MultiGRNBatchDetails.query.get(child_record.batch_detail_id)

        if not parent_record:
            logging.error(f"❌ Parent not found for batch_detail_id={child_record.batch_detail_id}")
            return jsonify({
                'success': False,
                'error': f'Parent batch record not found for this pack.'
            }), 404

        logging.info(f"Found: Child GRN={child_record.grn_number}, Parent GRN={parent_record.grn_number}, Parent ID={parent_record.id}")

        # ---------------------------
        # 5. Check if Already Verified
        # ---------------------------
        if child_record.status == 'verified':
            return jsonify({
                'success': True,
                'message': 'This pack is already verified.',
                'already_verified': True,
                'detail_type': 'batch',
                'item_info': {
                    'batch_number': parent_record.batch_number,
                    'quantity': float(child_record.qty_in_pack),
                    'grn_number': child_record.grn_number,
                    'parent_grn_number': parent_record.grn_number,
                    'parent_status': parent_record.status
                }
            })

        # ---------------------------
        # 6. Validate Quantity
        # ---------------------------
        db_qty = int(float(child_record.qty_in_pack))

        if qr_qty != db_qty:
            logging.error(f"❌ Quantity mismatch: QR={qr_qty}, DB={db_qty}")
            return jsonify({
                'success': False,
                'error': f"Quantity mismatch! QR label shows {qr_qty} but database expects {db_qty} for pack {grn_id}."
            }), 400

        # ---------------------------
        # 7. Mark Child (Pack) as Verified
        # ---------------------------
        child_record.status = 'verified'
        db.session.flush()  # Flush to ensure status is updated before counting
        logging.info(f"✅ Pack verified: GRN={child_record.grn_number}, Qty={db_qty}")

        # ---------------------------
        # 8. Check if ALL packs for THIS parent are verified
        # Using batch_detail_id relationship (more reliable than LIKE query)
        # ---------------------------
        total_packs = MultiGRNBatchDetailsLabel.query.filter_by(
            batch_detail_id=parent_record.id
        ).count()

        verified_packs = MultiGRNBatchDetailsLabel.query.filter_by(
            batch_detail_id=parent_record.id,
            status='verified'
        ).count()

        pending_count = total_packs - verified_packs

        logging.info(f"📦 Pack status for parent {parent_record.grn_number}: Total={total_packs}, Verified={verified_packs}, Pending={pending_count}")

        # ---------------------------
        # 9. If ALL packs verified → Update Parent status
        # ---------------------------
        if pending_count == 0 and total_packs > 0:
            parent_record.status = 'verified'
            logging.info(f"✅ All packs verified! Parent GRN {parent_record.grn_number} status updated to 'verified'")
            final_message = f"Pack verified successfully! All {total_packs} pack(s) completed — batch status updated to VERIFIED."
        else:
            final_message = f"Pack verified successfully! {verified_packs}/{total_packs} pack(s) verified, {pending_count} remaining."

        db.session.commit()

        # ---------------------------
        # 10. Final JSON response
        # ---------------------------
        return jsonify({
            'success': True,
            'message': final_message,
            'detail_type': 'batch',
            'item_info': {
                'batch_number': parent_record.batch_number,
                'quantity': float(child_record.qty_in_pack),
                'grn_number': child_record.grn_number,
                'parent_grn_number': parent_record.grn_number,
                'parent_status': parent_record.status,
                'total_packs': total_packs,
                'verified_packs': verified_packs,
                'pending_packs': pending_count
            }
        })

    except Exception as e:
        logging.error(f"❌ QR scan error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# @multi_grn_bp.route('/api/scan-qr-code', methods=['POST'])
# @login_required
# def scan_qr_code():
#     """API endpoint to scan QR code and mark line item as verified - with quantity validation"""
#     try:
#         data = request.get_json()
#         qr_data = data.get('qr_data', '')

#         if not qr_data:
#             return jsonify({'success': False, 'error': 'QR code data is required'}), 400

#         try:
#             qr_json = json.loads(qr_data)
#             grn_id = qr_json.get('id', '')  # Full GRN with pack number (e.g., MGN-13-22-1-1)
#             qr_qty = qr_json.get('qty', 0)  # Quantity from QR code
#         except:
#             return jsonify({'success': False, 'error': 'Invalid QR code format'}), 400

#         if not grn_id:
#             return jsonify({'success': False, 'error': 'QR code ID is missing'}), 400

#         logging.info(f"🔍 QR scan received: GRN ID={grn_id}, Qty={qr_qty}")

#         from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails, \
#             MultiGRNBatchDetailsLabel

#         # Parse GRN number to extract header and pack identifiers
#         # Example: MGN-13-22-1-1 → header: MGN-13-22, pack: MGN-13-22-1
#         parts = grn_id.split("-")
#         main_grn = "-".join(parts[:5])  # Pack GRN: MGN-13-22-1
#         main_grns = "-".join(parts[:4])  # Header GRN: MGN-13-22
        
#         logging.info(f"🔍 Searching DB for pack: {main_grn}, header: {main_grns}")

#         # Find the header in MultiGRNBatchDetails table
#         header_grn = MultiGRNBatchDetails.query.filter_by(grn_number=main_grns).first()
        
#         # Find the specific pack in MultiGRNBatchDetailsLabel table
#         line_item = MultiGRNBatchDetailsLabel.query.filter_by(grn_number=main_grn).first()
        
#         if not line_item:
#             logging.error(f"❌ Pack not found in database: GRN={grn_id}")
#             return jsonify({
#                 'success': False,
#                 'error': f'Pack {grn_id} not found in this batch. Please ensure you are scanning the correct QR label for this batch.'
#             }), 404
        
#         if not header_grn:
#             logging.error(f"❌ Header not found in database: GRN={main_grns}")
#             return jsonify({
#                 'success': False,
#                 'error': f'Header {main_grns} not found in database.'
#             }), 404

#         # Check if already verified
#         if line_item.status == 'verified':
#             logging.info(f"ℹ️ Pack already verified: GRN={grn_id}")
#             return jsonify({
#                 'success': True,
#                 'message': 'This pack was already verified',
#                 'already_verified': True,
#                 'detail_type': 'batch',
#                 'item_info': {
#                     'batch_number': header_grn.batch_number,
#                     'quantity': float(line_item.qty_in_pack),
#                     'grn_number': line_item.grn_number
#                 }
#             })

#         # Validate quantity matches (QR qty should match database quantity for this pack)
#         db_pack_qty = int(float(line_item.qty_in_pack))
#         qr_pack_qty = int(qr_qty)

#         if qr_pack_qty != db_pack_qty:
#             logging.error(f"❌ Quantity mismatch: GRN={grn_id}, QR Qty={qr_pack_qty}, DB Qty={db_pack_qty}")
#             return jsonify({
#                 'success': False,
#                 'error': f'Quantity mismatch! QR label shows {qr_pack_qty} but database expects {db_pack_qty} for pack {grn_id}. Please verify the correct label.'
#             }), 400

#         # 1. Mark this pack as verified
#         line_item.status = 'verified'
#         db.session.commit()
#         logging.info(f"✅ Pack verified: GRN={grn_id}, Batch={header_grn.batch_number}, Qty={qr_pack_qty}")

#         # 2. Check if ALL packs for THIS specific header are verified
#         # CRITICAL FIX: Only check packs belonging to this header (main_grns)
#         pending_packs_count = MultiGRNBatchDetailsLabel.query.filter(
#             MultiGRNBatchDetailsLabel.grn_number.like(f"{main_grns}-%"),
#             MultiGRNBatchDetailsLabel.status != 'verified'
#         ).count()

#         if pending_packs_count == 0:
#             # 3. All packs verified for this header → Update header status
#             header_grn.status = 'verified'
#             db.session.commit()
#             logging.info(f"✅ All packs verified for header {main_grns} - Header status updated to verified")
#             final_status = "All packs verified – header updated"
#         else:
#             logging.info(f"📦 {pending_packs_count} packs still pending for header {main_grns}")
#             final_status = f"{pending_packs_count} packs still pending"

#         return jsonify({
#             'success': True,
#             'message': f'Pack verified successfully! Batch: {header_grn.batch_number}, Qty: {qr_pack_qty} matched. {final_status}',
#             'detail_type': 'batch',
#             'item_info': {
#                 'batch_number': header_grn.batch_number,
#                 'quantity': float(line_item.qty_in_pack),
#                 'grn_number': line_item.grn_number
#             }
#         })

#     except Exception as e:
#         logging.error(f"❌ Error scanning QR code: {str(e)}")
#         db.session.rollback()
#         return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/batch/<int:batch_id>/verification-status')
@login_required
def batch_verification_status(batch_id):
    """API endpoint to get batch verification status"""
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails
        
        total_items = 0
        verified_items = 0
        
        for po_link in batch.po_links:
            for line in po_link.line_selections:
                batch_details = MultiGRNBatchDetails.query.filter_by(line_selection_id=line.id).all()
                serial_details = MultiGRNSerialDetails.query.filter_by(line_selection_id=line.id).all()
                
                for detail in batch_details:
                    total_items += 1
                    if detail.status == 'verified':
                        verified_items += 1
                
                for detail in serial_details:
                    total_items += 1
                    if detail.status == 'verified':
                        verified_items += 1
        
        all_verified = total_items > 0 and verified_items == total_items
        
        return jsonify({
            'success': True,
            'total_items': total_items,
            'verified_items': verified_items,
            'all_verified': all_verified,
            'percentage': round((verified_items / total_items * 100), 2) if total_items > 0 else 0
        })
    
    except Exception as e:
        logging.error(f"Error getting verification status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/search-customers')
@login_required
def api_search_customers():
    """API endpoint to search customers (legacy - kept for backward compatibility)"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify({'customers': []})
    
    sap_service = SAPMultiGRNService()
    result = sap_service.fetch_business_partners('S')
    
    if not result['success']:
        return jsonify({'error': result.get('error')}), 500
    
    partners = result.get('partners', [])
    filtered = [p for p in partners if query.lower() in p['CardName'].lower() or query.lower() in p['CardCode'].lower()]
    
    return jsonify({'customers': filtered[:20]})

@multi_grn_bp.route('/api/customers-dropdown')
@login_required
def api_customers_dropdown():
    """API endpoint to fetch all valid customers for dropdown"""
    sap_service = SAPMultiGRNService()
    result = sap_service.fetch_all_valid_customers()
    
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error')}), 500
    
    customers = result.get('customers', [])
    return jsonify({'success': True, 'customers': customers})

@multi_grn_bp.route('/api/po-series')
@login_required
def api_po_series():
    """API endpoint to fetch PO document series"""
    sap_service = SAPMultiGRNService()
    result = sap_service.fetch_po_series()
    
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error')}), 500
    
    return jsonify({'success': True, 'series': result.get('series', [])})

@multi_grn_bp.route('/api/cardcode-by-series/<series_id>')
@login_required
def api_cardcode_by_series(series_id):
    """API endpoint to fetch CardCodes filtered by Series ID"""
    sap_service = SAPMultiGRNService()
    result = sap_service.fetch_cardcode_by_series(series_id)
    
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error')}), 500
    
    return jsonify({'success': True, 'cardcodes': result.get('cardcodes', [])})

@multi_grn_bp.route('/api/pos-by-series-and-card')
@login_required
def api_pos_by_series_and_card():
    """API endpoint to fetch POs filtered by Series and CardCode"""
    series_id = request.args.get('series_id')
    card_code = request.args.get('card_code')
    
    if not series_id or not card_code:
        return jsonify({'success': False, 'error': 'series_id and card_code are required'}), 400
    
    sap_service = SAPMultiGRNService()
    result = sap_service.fetch_purchase_orders_by_series_and_card(series_id, card_code)
    
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error')}), 500
    
    return jsonify({'success': True, 'purchase_orders': result.get('purchase_orders', [])})

@multi_grn_bp.route('/api/generate-barcode', methods=['POST'])
@login_required
def generate_barcode():
    """Generate barcode/QR code for MultiGRN item"""
    try:
        data = request.get_json()
        item_code = data.get('item_code')
        item_name = data.get('item_name', '')
        batch_number = data.get('batch_number', '')
        serial_number = data.get('serial_number', '')
        grn_doc_num = data.get('grn_doc_num', '')
        batch_id = data.get('batch_id')
        
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400
        
        qr_string = f"{item_code}|{grn_doc_num}|{item_name}|{batch_number or serial_number or 'N/A'}"
        
        return jsonify({
            'success': True,
            'qr_data': qr_string,
            'label_info': {
                'item_code': item_code,
                'grn_doc_num': grn_doc_num,
                'item_name': item_name,
                'batch_number': batch_number,
                'serial_number': serial_number,
                'batch_id': batch_id
            }
        })
        
    except Exception as e:
        logging.error(f"Error generating barcode: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/validate-item', methods=['POST'])
@login_required
def validate_item():
    """Validate item code and return batch/serial management info"""
    try:
        data = request.get_json()
        item_code = data.get('item_code')
        
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400
        
        sap_service = SAPMultiGRNService()
        
        # Validate item and get batch/serial info
        validation_result = sap_service.validate_item_code(item_code)
        
        if not validation_result['success']:
            return jsonify(validation_result), 404
        
        # Get item details (name, UoM, etc.)
        details_result = sap_service.get_item_details(item_code)
        
        if details_result['success']:
            validation_result['item_name'] = details_result['item'].get('ItemName', '')
            validation_result['uom'] = details_result['item'].get('InventoryUOM', '')
        
        return jsonify(validation_result)
        
    except Exception as e:
        logging.error(f"Error validating item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/validate-item/<item_code>', methods=['GET'])
@login_required
def validate_item_get(item_code):
    """Validate item code via GET request (for JavaScript calls)"""
    try:
        if not item_code:
            return jsonify({'success': False, 'error': 'Item code is required'}), 400
        
        sap_service = SAPMultiGRNService()
        
        # Validate item and get batch/serial info
        validation_result = sap_service.validate_item_code(item_code)
        
        if not validation_result['success']:
            return jsonify(validation_result), 404
        
        # Get item details (name, UoM, etc.)
        details_result = sap_service.get_item_details(item_code)
        
        if details_result['success']:
            validation_result['item_name'] = details_result['item'].get('ItemName', '')
            validation_result['uom'] = details_result['item'].get('InventoryUOM', '')
        
        return jsonify(validation_result)
        
    except Exception as e:
        logging.error(f"Error validating item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/update-line-item', methods=['POST'])
@login_required
def update_line_item():
    """Update line item details with warehouse, bin location, quantity, and number of bags"""
    try:
        data = request.get_json()
        
        line_selection_id = data.get('line_selection_id')
        quantity = data.get('quantity')
        warehouse_code = data.get('warehouse_code')
        bin_location = data.get('bin_location')
        # Support both 'expiry_date' and 'expiration_date' for backward compatibility
        expiration_date = data.get('expiry_date') or data.get('expiration_date')
        number_of_bags = data.get('number_of_bags')
        
        if not line_selection_id:
            return jsonify({'success': False, 'error': 'Line selection ID is required'}), 400
        
        # Get the line selection
        line_selection = MultiGRNLineSelection.query.get(line_selection_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line item not found'}), 404
        
        # Update fields
        if quantity:
            line_selection.selected_quantity = Decimal(str(quantity))
        if warehouse_code:
            line_selection.warehouse_code = warehouse_code
        if bin_location:
            line_selection.bin_location = bin_location
        
        # Handle expiration date (supports both field names for compatibility)
        expiry_date_obj = None
        sap = SAPIntegration()
        itemType = sap.validate_item_code(line_selection.item_code)
        if expiration_date:
            try:
                from datetime import datetime
                if itemType.get("serial_num") == 'Y':
                    expiry_date_obj = datetime.strptime(expiration_date, '%Y-%m-%d').date()
                elif itemType.get("batch_num") == 'Y':
                    expiry_date_obj = datetime.strptime(expiration_date, '%Y-%m-%d').date()
                else:
                    expiry_date_obj = ''
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid expiration date format'}), 400
        
        # Handle number of bags - create ONE batch_detail + N labels
        if number_of_bags and int(number_of_bags) > 0:
            from modules.multi_grn_creation.models import MultiGRNBatchDetails
            from datetime import datetime
            import io
            import base64
            import qrcode
            
            # Clear existing batch details and labels for this line (cascade delete handles labels automatically)
            existing_batches = MultiGRNBatchDetails.query.filter_by(line_selection_id=line_selection_id).all()
            for batch in existing_batches:
                db.session.delete(batch)  # Labels are deleted automatically via cascade
            db.session.flush()
            
            bags_count = int(number_of_bags)
            
            # Get batch ID from the line's PO link for unique GRN numbering
            if line_selection.po_link and hasattr(line_selection.po_link, 'batch_id'):
                batch_id = line_selection.po_link.batch_id
            else:
                batch_id = line_selection_id


            # Auto-generate batch number using date and item code (YYYYMMDD-ITEMCODE-1)
            today_str = datetime.now().strftime('%Y%m%d')
            item_code_short = line_selection.item_code[:10] if line_selection.item_code else "ITEM"
           # batch_number = f"{today_str}-{item_code_short}-1"
            if itemType.get("serial_num") == 'Y':
             #batch_number = f"{today_str}"
             batch_number = f"{today_str}-{line_selection.item_code}"
            elif itemType.get("batch_num") == 'Y' :
                batch_number = f"{today_str}-{line_selection.item_code}"
            else:
                batch_number = ''

            # Calculate quantity distribution across packs (INTEGER ONLY)
            if line_selection.selected_quantity:
                total_qty_original = Decimal(str(line_selection.selected_quantity))
                total_qty_int = int(total_qty_original.to_integral_value(rounding=ROUND_HALF_UP))
                
                # Create ONE batch_detail record with total quantity
                batch_detail = MultiGRNBatchDetails(
                    line_selection_id=line_selection_id,
                    batch_number=batch_number,
                    quantity=Decimal(str(total_qty_int)),
                    expiry_date=expiry_date_obj,
                    grn_number=f"MGN-{batch_id}-{line_selection_id}-1",
                    qty_per_pack=Decimal(str(total_qty_int)) / bags_count,
                    no_of_packs=bags_count
                )
                db.session.add(batch_detail)
                db.session.flush()
                
                # Distribute quantity across packs using helper function
                pack_quantities = distribute_quantity_to_packs(total_qty_int, bags_count)
                
                # Get PO number and GRN date for QR code data
                po_number = line_selection.po_link.po_doc_num if line_selection.po_link else 'N/A'
                grn_date = datetime.now().strftime('%Y-%m-%d')
                
                # Create individual label records for each pack
                for pack_num in range(1, bags_count + 1):
                    pack_qty = pack_quantities[pack_num - 1]
                    grn_number = f"MGN-{batch_id}-{line_selection_id}-1-{pack_num}"
                    
                    # Generate QR barcode for this pack with complete data
                    qr_data = {
                        'id': grn_number,
                        'po': str(po_number),
                        'item': line_selection.item_code,
                        'batch': batch_number,
                        'qty': pack_qty,
                        'pack': f"{pack_num} of {bags_count}",
                        'grn_date': grn_date,
                        'exp_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else 'N/A',
                        'bin': line_selection.bin_location or 'N/A'
                    }
                    qr_text = json.dumps(qr_data)
                    
                    try:
                        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                        qr.add_data(qr_text)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        buffer = io.BytesIO()
                        img.save(buffer, format='PNG')
                        buffer.seek(0)
                        barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
                    except Exception as e:
                        logging.error(f"Error generating QR code: {str(e)}")
                        barcode = None
                    
                    # Create label record
                    label = MultiGRNBatchDetailsLabel(
                        batch_detail_id=batch_detail.id,
                        pack_number=pack_num,
                        qty_in_pack=pack_qty,
                        grn_number=grn_number,
                        barcode=barcode,
                        qr_data=qr_text
                    )
                    db.session.add(label)
                    logging.info(f"✅ Created pack label {pack_num}/{bags_count}: GRN={grn_number}, Qty={pack_qty}")
                
                logging.info(f"✅ Created 1 batch_detail + {bags_count} pack labels for line {line_selection_id}: Total Qty={total_qty_int}, Batch={batch_number}")
            else:
                logging.warning(f"⚠️ No quantity selected for line {line_selection_id}, skipping pack creation")
        
        db.session.commit()
        
        logging.info(f"✅ Updated line item {line_selection_id}: Qty={quantity}, Warehouse={warehouse_code}, Bin={bin_location}, Bags={number_of_bags}")
        
        return jsonify({
            'success': True,
            'message': 'Line item updated successfully',
            'line_selection_id': line_selection_id
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating line item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/add-manual-item', methods=['POST'])
@login_required
def add_manual_item():
    """Add a manual item to a PO link"""
    try:
        # Parse and validate JSON request body
        data = request.get_json()
        if data is None:
            return jsonify({'success': False, 'error': 'Invalid or missing JSON request body'}), 400
        
        po_link_id = data.get('po_link_id')
        item_code = data.get('item_code')
        item_description = data.get('item_description')
        quantity = data.get('quantity')
        uom = data.get('uom')
        warehouse_code = data.get('warehouse_code')
        bin_location = data.get('bin_location')
        batch_number = data.get('batch_number')
        expiry_date = data.get('expiry_date')
        serial_number = data.get('serial_number')
        supplier_barcode = data.get('supplier_barcode')
        
        if not all([po_link_id, item_code, quantity]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    except Exception as parse_error:
        # Catch JSON parsing errors (BadRequest, etc.)
        return jsonify({'success': False, 'error': f'Invalid JSON format: {str(parse_error)}'}), 400
    
    try:
        
        # Validate quantity format early
        try:
            quantity_decimal = Decimal(str(quantity))
            if quantity_decimal <= 0:
                return jsonify({'success': False, 'error': 'Quantity must be positive'}), 400
        except (ValueError, TypeError, InvalidOperation):
            return jsonify({'success': False, 'error': 'Invalid quantity format (must be numeric)'}), 400
        
        po_link = MultiGRNPOLink.query.get(po_link_id)
        if not po_link:
            return jsonify({'success': False, 'error': 'PO link not found'}), 404
        
        # Check if item already exists in line selections
        existing_line = MultiGRNLineSelection.query.filter_by(
            po_link_id=po_link_id,
            item_code=item_code
        ).first()
        
        if existing_line:
            return jsonify({'success': False, 'error': 'Item already exists in this PO'}), 400
        
        # SERVER-SIDE VALIDATION: Validate item code with SAP to get canonical inventory type
        sap_service = SAPMultiGRNService()
        validation_result = sap_service.validate_item_code(item_code)
        
        if not validation_result['success']:
            return jsonify({'success': False, 'error': f'Item validation failed: {validation_result.get("error")}'}), 400
        
        # Use server-validated inventory type, not client-provided value
        inventory_type = validation_result['inventory_type']
        batch_managed = validation_result['batch_managed']
        serial_managed = validation_result['serial_managed']
        management_method = validation_result.get('management_method', 'A')
        
        # Create new line selection with complete SAP validation fields
        line_selection = MultiGRNLineSelection(
            po_link_id=po_link_id,
            po_line_num=-1,  # Manual item, not from PO line
            item_code=item_code,
            item_description=item_description or '',
            ordered_quantity=Decimal(str(quantity)),
            open_quantity=Decimal(str(quantity)),
            selected_quantity=Decimal(str(quantity)),
            warehouse_code=warehouse_code or '7000-FG',
            bin_location=bin_location,
            unit_price=Decimal('0'),
            line_status='manual',
            inventory_type=inventory_type,
            batch_required='Y' if batch_managed else 'N',
            serial_required='Y' if serial_managed else 'N',
            manage_method=management_method
        )
        
        # SERVER-SIDE VALIDATION: Handle batch/serial numbers based on server-validated type
        if batch_managed:
            batch_numbers_data = data.get('batch_numbers')
            if not batch_numbers_data:
                return jsonify({'success': False, 'error': 'Batch numbers are required for batch-managed items'}), 400
            
            # Parse JSON if string
            if isinstance(batch_numbers_data, str):
                try:
                    batch_array = json.loads(batch_numbers_data)
                except json.JSONDecodeError:
                    return jsonify({'success': False, 'error': 'Invalid batch numbers JSON format'}), 400
            else:
                batch_array = batch_numbers_data
            
            # Validate batch array
            if not isinstance(batch_array, list) or len(batch_array) == 0:
                return jsonify({'success': False, 'error': 'At least one batch entry is required'}), 400
            
            total_batch_qty = Decimal('0')
            for idx, batch in enumerate(batch_array):
                # Validate entry is a dict
                if not isinstance(batch, dict):
                    return jsonify({'success': False, 'error': f'Batch #{idx+1}: Invalid batch entry format (must be an object)'}), 400
                
                # Validate required fields
                if not batch.get('BatchNumber'):
                    return jsonify({'success': False, 'error': f'Batch #{idx+1}: BatchNumber is required'}), 400
                if not batch.get('Quantity'):
                    return jsonify({'success': False, 'error': f'Batch #{idx+1}: Quantity is required'}), 400
                
                try:
                    batch_qty = Decimal(str(batch['Quantity']))
                    if batch_qty <= 0:
                        return jsonify({'success': False, 'error': f'Batch #{idx+1}: Quantity must be positive'}), 400
                    total_batch_qty += batch_qty
                except (ValueError, TypeError, InvalidOperation):
                    return jsonify({'success': False, 'error': f'Batch #{idx+1}: Invalid quantity format (must be numeric)'}), 400
            
            # Validate total batch quantity matches item quantity
            item_qty = Decimal(str(quantity))
            if abs(total_batch_qty - item_qty) > Decimal('0.001'):
                return jsonify({'success': False, 'error': f'Total batch quantity ({total_batch_qty}) must equal item quantity ({item_qty})'}), 400
            
            # Store normalized JSON
            line_selection.batch_numbers = json.dumps(batch_array)
        
        elif serial_managed:
            serial_numbers_data = data.get('serial_numbers')
            if not serial_numbers_data:
                return jsonify({'success': False, 'error': 'Serial numbers are required for serial-managed items'}), 400
            
            # Validate quantity is a positive integer for serial-managed items
            try:
                item_qty_decimal = Decimal(str(quantity))
                if item_qty_decimal <= 0:
                    return jsonify({'success': False, 'error': 'Quantity must be positive for serial-managed items'}), 400
                
                # Check if quantity is an integer
                if item_qty_decimal % 1 != 0:
                    return jsonify({'success': False, 'error': 'Quantity must be a whole number for serial-managed items (one serial per unit)'}), 400
                
                item_qty = int(item_qty_decimal)
            except (ValueError, TypeError, InvalidOperation):
                return jsonify({'success': False, 'error': 'Invalid quantity format (must be numeric)'}), 400
            
            # Parse JSON if string
            if isinstance(serial_numbers_data, str):
                try:
                    serial_array = json.loads(serial_numbers_data)
                except json.JSONDecodeError:
                    return jsonify({'success': False, 'error': 'Invalid serial numbers JSON format'}), 400
            else:
                serial_array = serial_numbers_data
            
            # Validate serial array
            if not isinstance(serial_array, list) or len(serial_array) == 0:
                return jsonify({'success': False, 'error': 'At least one serial number is required'}), 400
            
            # Validate exact 1:1 ratio between serial entries and quantity
            if len(serial_array) != item_qty:
                return jsonify({'success': False, 'error': f'Number of serial entries ({len(serial_array)}) must exactly equal quantity ({item_qty})'}), 400
            
            # Validate each serial entry
            for idx, serial in enumerate(serial_array):
                # Validate entry is a dict
                if not isinstance(serial, dict):
                    return jsonify({'success': False, 'error': f'Serial #{idx+1}: Invalid serial entry format (must be an object)'}), 400
                
                # Validate required fields
                if not serial.get('ManufacturerSerialNumber'):
                    return jsonify({'success': False, 'error': f'Serial #{idx+1}: ManufacturerSerialNumber is required'}), 400
                if not serial.get('InternalSerialNumber'):
                    return jsonify({'success': False, 'error': f'Serial #{idx+1}: InternalSerialNumber is required'}), 400
            
            # Store normalized JSON
            line_selection.serial_numbers = json.dumps(serial_array)
        
        db.session.add(line_selection)
        db.session.commit()
        
        logging.info(f"✅ Manual item {item_code} added to PO link {po_link_id} (type: {inventory_type})")
        return jsonify({
            'success': True,
            'message': 'Item added successfully',
            'line_id': line_selection.id
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding manual item: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/line-selections/<int:line_id>/batch-details', methods=['GET', 'POST'])
@login_required
def manage_batch_details(line_id):
    """Get or add batch number details for a Multi GRN line selection"""
    from modules.multi_grn_creation.models import MultiGRNBatchDetails
    import io
    import base64
    import qrcode
    
    line_selection = MultiGRNLineSelection.query.get_or_404(line_id)
    
    if request.method == 'GET':
        batches = [{
            'id': bn.id,
            'batch_number': bn.batch_number,
            'quantity': float(bn.quantity),
            'manufacturer_serial_number': bn.manufacturer_serial_number,
            'internal_serial_number': bn.internal_serial_number,
            'expiry_date': bn.expiry_date.isoformat() if bn.expiry_date else None,
            'barcode': bn.barcode,
            'grn_number': bn.grn_number,
            'qty_per_pack': float(bn.qty_per_pack) if bn.qty_per_pack else None,
            'no_of_packs': bn.no_of_packs
        } for bn in line_selection.batch_details]
        
        return jsonify({'success': True, 'batch_details': batches})
    
    elif request.method == 'POST':
        try:
            data = request.json
            
            batch_num = data.get('batch_number', '').strip()
            if not batch_num:
                return jsonify({'success': False, 'error': 'Batch number is required'}), 400
            
            quantity = float(data.get('quantity', 0))
            if quantity <= 0:
                return jsonify({'success': False, 'error': 'Quantity must be greater than 0'}), 400
            
            expiry_date_obj = None
            if data.get('expiry_date'):
                try:
                    expiry_date_obj = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid expiry date format'}), 400
            
            no_of_packs = int(data.get('no_of_packs', 1))
            
            # Get batch ID and line ID for GRN generation
            if line_selection.po_link and hasattr(line_selection.po_link, 'batch_id'):
                batch_id = line_selection.po_link.batch_id
            else:
                batch_id = line_id
            
            # Create ONE batch_detail record with total quantity
            batch = MultiGRNBatchDetails(
                line_selection_id=line_id,
                batch_number=batch_num,
                quantity=Decimal(str(quantity)),
                manufacturer_serial_number=data.get('manufacturer_serial_number'),
                internal_serial_number=data.get('internal_serial_number'),
                expiry_date=expiry_date_obj,
                barcode=None,
                grn_number=f"MGN-{batch_id}-{line_id}-1",
                qty_per_pack=Decimal(str(quantity)) / no_of_packs,
                no_of_packs=no_of_packs
            )
            db.session.add(batch)
            db.session.flush()
            
            # Distribute quantity across packs
            pack_quantities = distribute_quantity_to_packs(quantity, no_of_packs)
            
            # Get PO number and GRN date for QR code data
            po_number = line_selection.po_link.po_doc_num if line_selection.po_link else 'N/A'
            grn_date = datetime.now().strftime('%Y-%m-%d')
            
            # Create individual label records for each pack
            created_packs = []
            for pack_num in range(1, no_of_packs + 1):
                pack_qty = pack_quantities[pack_num - 1]
                grn_number = f"MGN-{batch_id}-{line_id}-1-{pack_num}"
                
                # Generate QR barcode for this pack with complete data
                qr_data = {
                    'id': grn_number,
                    'po': str(po_number),
                    'item': line_selection.item_code,
                    'batch': batch_num,
                    'qty': pack_qty,
                    'pack': f"{pack_num} of {no_of_packs}",
                    'grn_date': grn_date,
                    'exp_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else 'N/A',
                    'bin': line_selection.bin_location or 'N/A'
                }
                qr_text = json.dumps(qr_data)
                
                try:
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                    qr.add_data(qr_text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    buffer.seek(0)
                    barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
                except Exception as e:
                    logging.error(f"Error generating QR code: {str(e)}")
                    barcode = None
                
                # Create label record
                label = MultiGRNBatchDetailsLabel(
                    batch_detail_id=batch.id,
                    pack_number=pack_num,
                    qty_in_pack=pack_qty,
                    grn_number=grn_number,
                    barcode=barcode,
                    qr_data=qr_text
                )
                db.session.add(label)
                
                created_packs.append({
                    'pack_num': pack_num,
                    'grn_number': grn_number,
                    'quantity': pack_qty
                })
                logging.info(f"✅ Created pack label {pack_num}/{no_of_packs}: GRN={grn_number}, Qty={pack_qty}")
            
            db.session.commit()
            
            logging.info(f"✅ Added batch {batch_num} for line selection {line_id}: {no_of_packs} pack label(s) created")
            return jsonify({
                'success': True,
                'batch': {
                    'id': batch.id,
                    'batch_number': batch_num,
                    'quantity': float(quantity),
                    'no_of_packs': no_of_packs,
                    'packs_created': created_packs
                }
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error adding batch details: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/line-selections/<int:line_id>/serial-details', methods=['GET', 'POST'])
@login_required
def manage_serial_details(line_id):
    """Get or add serial number details for a Multi GRN line selection"""
    from modules.multi_grn_creation.models import MultiGRNSerialDetails
    import io
    import base64
    import qrcode
    
    line_selection = MultiGRNLineSelection.query.get_or_404(line_id)
    
    if request.method == 'GET':
        serials = [{
            'id': sn.id,
            'serial_number': sn.serial_number,
            'manufacturer_serial_number': sn.manufacturer_serial_number,
            'internal_serial_number': sn.internal_serial_number,
            'expiry_date': sn.expiry_date.isoformat() if sn.expiry_date else None,
            'barcode': sn.barcode,
            'grn_number': sn.grn_number,
            'qty_per_pack': float(sn.qty_per_pack) if sn.qty_per_pack else 1,
            'no_of_packs': sn.no_of_packs
        } for sn in line_selection.serial_details]
        
        return jsonify({'success': True, 'serial_details': serials})
    
    elif request.method == 'POST':
        try:
            data = request.json
            
            serial_num = data.get('serial_number', '').strip()
            if not serial_num:
                return jsonify({'success': False, 'error': 'Serial number is required'}), 400
            
            expiry_date_obj = None
            if data.get('expiry_date'):
                try:
                    expiry_date_obj = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid expiry date format'}), 400
            
            barcode_data = f"SERIAL:{serial_num}"
            try:
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                qr.add_data(barcode_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            except Exception:
                barcode = None
            
            serial = MultiGRNSerialDetails(
                line_selection_id=line_id,
                serial_number=serial_num,
                manufacturer_serial_number=data.get('manufacturer_serial_number'),
                internal_serial_number=data.get('internal_serial_number'),
                expiry_date=expiry_date_obj,
                barcode=barcode,
                grn_number=data.get('grn_number'),
                qty_per_pack=data.get('qty_per_pack', 1),
                no_of_packs=data.get('no_of_packs', 1)
            )
            
            db.session.add(serial)
            db.session.commit()
            
            logging.info(f"✅ Added serial {serial_num} for line selection {line_id}")
            return jsonify({
                'success': True,
                'serial': {
                    'id': serial.id,
                    'serial_number': serial.serial_number,
                    'barcode': serial.barcode
                }
            })
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error adding serial details: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

def generate_barcode_multi_grn(data):
    """Generate QR code barcode and return base64 encoded image"""
    import io
    import base64
    import qrcode
    
    try:
        if not data or len(str(data).strip()) == 0:
            logging.warning("⚠️ Empty data provided for barcode generation")
            return None
        
        data_str = str(data).strip()
        if len(data_str) > 500:
            logging.warning(f"⚠️ Barcode data too long ({len(data_str)} chars), truncating to 500")
            data_str = data_str[:500]
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data_str)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        if len(img_base64) > 100000:
            logging.warning(f"⚠️ Generated barcode too large ({len(img_base64)} bytes), skipping")
            return None
        
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        logging.error(f"❌ Error generating barcode for data '{str(data)[:50]}...': {str(e)}")
        return None

@multi_grn_bp.route('/api/generate-barcode-labels', methods=['POST'])
@login_required
def generate_barcode_labels_multi_grn():
    """
    API endpoint to generate QR code labels for Multi GRN items (Serial, Batch, and Non-managed)
    Accepts: batch_id, line_selection_id, label_type ('serial', 'batch', or 'regular')
    Returns: JSON with label data including all requested fields
    """
    try:
        data = request.get_json()
        
        batch_id = int(data.get('batch_id'))  # Convert to int for proper comparison
        line_selection_id = int(data.get('line_selection_id'))  # Convert to int
        label_type = data.get('label_type', 'batch')
        
        logging.info(f"🏷️ Generate barcode labels request: batch_id={batch_id}, line_selection_id={line_selection_id}, label_type={label_type}")
        
        if not all([batch_id, line_selection_id]):
            logging.error("❌ Missing required parameters")
            return jsonify({
                'success': False,
                'error': 'Missing required parameters: batch_id, line_selection_id'
            }), 400
        
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        line_selection = MultiGRNLineSelection.query.get_or_404(line_selection_id)
        
        if batch.user_id != current_user.id and current_user.role not in ['admin', 'manager']:
            return jsonify({
                'success': False,
                'error': 'Access denied'
            }), 403
        
        # Ensure proper integer comparison
        if line_selection.po_link.batch_id != batch_id:
            logging.error(f"Batch ID mismatch: line_selection.po_link.batch_id={line_selection.po_link.batch_id}, batch_id={batch_id}")
            return jsonify({
                'success': False,
                'error': 'Line selection does not belong to this batch'
            }), 400
        
        grn_date = batch.created_at.strftime('%Y-%m-%d')
        doc_number = batch.batch_number or f"MGRN/{batch.id}"
        po_number = line_selection.po_link.po_doc_num
        
        labels = []
        
        # Check if item has batch_details (even if not batch-managed) for pack generation
        has_batch_details = len(line_selection.batch_details) > 0
        has_serial_details = len(line_selection.serial_details) > 0
        
        logging.info(f"📊 Line selection data: item_code={line_selection.item_code}, has_batch_details={has_batch_details} (count={len(line_selection.batch_details)}), has_serial_details={has_serial_details} (count={len(line_selection.serial_details)})")
        
        if label_type == 'serial':
            logging.info(f"🔖 Processing SERIAL labels")
            serial_details = line_selection.serial_details
            total_serials = len(serial_details)
            
            if total_serials == 0:
                logging.warning(f"⚠️ No serial numbers found for line_selection_id={line_selection_id}")
                return jsonify({
                    'success': False,
                    'error': 'No serial numbers found for this item'
                }), 400
            
            first_serial = serial_details[0]
            num_packs = first_serial.no_of_packs if first_serial.no_of_packs else total_serials
            qty_per_pack = first_serial.qty_per_pack if first_serial.qty_per_pack else 1
            
            if num_packs > 0 and total_serials % num_packs != 0:
                return jsonify({
                    'success': False,
                    'error': f'Data inconsistency: {total_serials} serials cannot be evenly divided into {num_packs} packs'
                }), 400
            
            serials_per_pack = total_serials // num_packs if num_packs > 0 else total_serials
            
            for pack_idx in range(1, num_packs + 1):
                pack_start = (pack_idx - 1) * serials_per_pack
                pack_end = pack_start + serials_per_pack
                pack_serials = serial_details[pack_start:pack_end]
                
                if not pack_serials:
                    return jsonify({
                        'success': False,
                        'error': f'Data inconsistency: Pack {pack_idx} has no serial numbers'
                    }), 400
                
                ref_serial = pack_serials[0]
                serial_grn = ref_serial.grn_number or doc_number
                
                serial_list = ', '.join([s.serial_number for s in pack_serials])
                
                qr_data = {
                    'id': f"{serial_grn}-{pack_idx}",
                    'po': str(po_number),
                    'item': line_selection.item_code,
                    'batch': 'N/A',
                    'serial': serial_list,
                    'qty': int(qty_per_pack),
                    'pack': f"{pack_idx} of {num_packs}",
                    'grn_date': grn_date,
                    'exp_date': ref_serial.expiry_date.strftime('%Y-%m-%d') if ref_serial.expiry_date else 'N/A',
                    'bin': line_selection.bin_location or 'N/A'
                }
                
                qr_text = json.dumps(qr_data)
                qr_code_image = generate_barcode_multi_grn(qr_text)
                
                label = {
                    'sequence': pack_idx,
                    'total': num_packs,
                    'pack_text': f"{pack_idx} of {num_packs}",
                    'po_number': po_number,
                    'serial_number': serial_list,
                    'quantity': float(qty_per_pack),
                    'qty_per_pack': float(qty_per_pack),
                    'no_of_packs': num_packs,
                    'grn_date': grn_date,
                    'grn_number': f"{serial_grn}-{pack_idx}",
                    'expiration_date': ref_serial.expiry_date.strftime('%Y-%m-%d') if ref_serial.expiry_date else 'N/A',
                    'item_code': line_selection.item_code,
                    'item_name': line_selection.item_description or '',
                    'doc_number': f"{serial_grn}-{pack_idx}",
                    'bin_location': line_selection.bin_location or 'N/A',
                    'qr_code_image': qr_code_image,
                    'qr_data': qr_data
                }
                labels.append(label)
        
        elif label_type == 'batch':
            logging.info(f"🔖 Processing BATCH labels")
            batch_details = line_selection.batch_details
            
            logging.debug(f"   Found {len(batch_details)} batch detail records for line_selection_id={line_selection_id}")
            for bd in batch_details:
                logging.debug(f"      Batch: {bd.batch_number}, Qty: {bd.quantity}, Packs: {bd.no_of_packs}, GRN: {bd.grn_number}")
            
            if len(batch_details) == 0:
                logging.warning(f"⚠️ No batch details found for line_selection_id={line_selection_id}, but label_type='batch' was requested")
                logging.warning(f"   Item: {line_selection.item_code}, Batch Required: {line_selection.batch_required}, Manage Method: {line_selection.manage_method}")
                return jsonify({
                    'success': False,
                    'error': 'No batch details found for this item. Please add item details first before printing labels.'
                }), 400
            
            # Get the batch detail record
            batch_detail = batch_details[0]
            num_packs = batch_detail.no_of_packs or 1
            
            # Get label records from the new linking table
            pack_labels = batch_detail.pack_labels
            
            if len(pack_labels) == 0:
                logging.warning(f"⚠️ No pack labels found for batch_detail_id={batch_detail.id}")
                return jsonify({
                    'success': False,
                    'error': 'No pack labels found. Please regenerate the batch details.'
                }), 400
            
            # Generate labels from stored pack label records
            for pack_label in pack_labels:
                # Check if qr_data exists and is valid JSON, otherwise regenerate it
                needs_regeneration = False
                qr_data_dict = None
                
                if pack_label.qr_data:
                    try:
                        qr_data_dict = json.loads(pack_label.qr_data)
                        # Check if all required fields are present (regenerate if missing po, item, or grn_date)
                        required_fields = ['id', 'po', 'item', 'batch', 'qty', 'pack', 'grn_date', 'exp_date']
                        missing_fields = [f for f in required_fields if f not in qr_data_dict]
                        if missing_fields:
                            logging.info(f"🔄 qr_data for pack_label {pack_label.id} is missing fields {missing_fields}, regenerating")
                            needs_regeneration = True
                    except (json.JSONDecodeError, TypeError) as e:
                        logging.warning(f"⚠️ Invalid qr_data for pack_label {pack_label.id}, regenerating: {e}")
                        needs_regeneration = True
                else:
                    logging.info(f"🔄 Missing qr_data for pack_label {pack_label.id} (GRN: {pack_label.grn_number}), regenerating")
                    needs_regeneration = True
                
                # Regenerate qr_data if missing, invalid, or incomplete
                if needs_regeneration:
                    qr_data_dict = {
                        'id': pack_label.grn_number,
                        'po': str(po_number),
                        'item': line_selection.item_code,
                        'batch': batch_detail.batch_number,
                        'qty': int(pack_label.qty_in_pack) if pack_label.qty_in_pack else 1,
                        'pack': f"{pack_label.pack_number} of {num_packs}",
                        'grn_date': grn_date,
                        'exp_date': batch_detail.expiry_date or 'N/A',
                        'bin': line_selection.bin_location or 'N/A'
                    }
                    # Save regenerated qr_data back to database for future use
                    pack_label.qr_data = json.dumps(qr_data_dict)
                    logging.info(f"✅ Regenerated and saved qr_data for pack_label {pack_label.id}")
                    
                    # Regenerate barcode with new qr_data
                    qr_text = json.dumps(qr_data_dict)
                    qr_code_image = generate_barcode_multi_grn(qr_text)
                    if qr_code_image:
                        pack_label.barcode = qr_code_image
                        logging.info(f"✅ Regenerated barcode for pack_label {pack_label.id}")
                else:
                    # Use stored barcode or regenerate if missing
                    if pack_label.barcode:
                        qr_code_image = pack_label.barcode
                    else:
                        qr_text = json.dumps(qr_data_dict)
                        qr_code_image = generate_barcode_multi_grn(qr_text)
                        if qr_code_image:
                            pack_label.barcode = qr_code_image
                
                label = {
                    'sequence': pack_label.pack_number,
                    'total': num_packs,
                    'pack_text': f"{pack_label.pack_number} of {num_packs}",
                    'po_number': po_number,
                    'batch_number': batch_detail.batch_number,
                    'quantity': float(batch_detail.quantity),
                    'qty_per_pack': int(pack_label.qty_in_pack) if pack_label.qty_in_pack else 1,
                    'no_of_packs': num_packs,
                    'grn_date': grn_date,
                    'grn_number': pack_label.grn_number,
                    #'expiration_date': batch_detail.expiry_date.strftime('%Y-%m-%d') if batch_detail.expiry_date else 'N/A',
                    'expiration_date':  batch_detail.expiry_date or 'N/A',
                    'item_code': line_selection.item_code,
                    'item_name': line_selection.item_description or '',
                    'doc_number': pack_label.grn_number,
                    'bin_location': line_selection.bin_location or 'N/A',
                    'qr_code_image': qr_code_image,
                    'qr_data': qr_data_dict
                }
                labels.append(label)
                
                # Mark label as printed
                pack_label.printed = True
                pack_label.printed_at = datetime.utcnow()
            
            db.session.commit()
        
        # Handle standard items with batch_details (created via number_of_packs)
        elif has_batch_details and label_type == 'regular':
            logging.info(f"🔖 Processing REGULAR labels with batch_details")
            batch_details = line_selection.batch_details
            
            # Get the single batch detail record
            batch_detail = batch_details[0]
            num_packs = batch_detail.no_of_packs or 1
            batch_grn = batch_detail.grn_number or doc_number
            
            # Calculate integer distribution across packs (first packs get remainder)
            total_quantity = batch_detail.quantity
            pack_quantities = distribute_quantity_to_packs(total_quantity, num_packs)
            
            # Generate multiple labels based on no_of_packs field
            for pack_num in range(1, num_packs + 1):
                pack_qty = pack_quantities[pack_num - 1]  # Get specific quantity for this pack
                
                qr_data = {
                    'id': f"{batch_grn}-{pack_num}",
                    'po': str(po_number),
                    'item': line_selection.item_code,
                    'batch': batch_detail.batch_number,
                    'qty': pack_qty,
                    'pack': f"{pack_num} of {num_packs}",
                    'grn_date': grn_date,
                    'exp_date': batch_detail.expiry_date or 'N/A',
                    'bin': line_selection.bin_location or 'N/A'
                }
                
                qr_text = json.dumps(qr_data)
                qr_code_image = generate_barcode_multi_grn(qr_text)
                
                label = {
                    'sequence': pack_num,
                    'total': num_packs,
                    'pack_text': f"{pack_num} of {num_packs}",
                    'po_number': po_number,
                    'batch_number': batch_detail.batch_number,
                    'quantity': float(batch_detail.quantity),
                    'qty_per_pack': pack_qty,
                    'no_of_packs': num_packs,
                    'grn_date': grn_date,
                    'grn_number': f"{batch_grn}-{pack_num}",
                    'expiration_date': batch_detail.expiry_date or 'N/A',
                    'item_code': line_selection.item_code,
                    'item_name': line_selection.item_description or '',
                    'doc_number': f"{batch_grn}-{pack_num}",
                    'bin_location': line_selection.bin_location or 'N/A',
                    'qr_code_image': qr_code_image,
                    'qr_data': qr_data
                }
                labels.append(label)
        
        # Handle regular items without batch_details (single label, no packs)
        else:
            logging.info(f"🔖 Processing REGULAR labels without batch_details (single label)")
            qr_data = {
                'id': doc_number,
                'po': str(po_number),
                'item': line_selection.item_code,
                'batch': 'N/A',
                'qty': int(float(line_selection.selected_quantity)),
                'pack': '1 of 1',
                'grn_date': grn_date,
                'exp_date': 'N/A',
                'bin': line_selection.bin_location or 'N/A'
            }
            
            qr_text = json.dumps(qr_data)
            qr_code_image = generate_barcode_multi_grn(qr_text)
            
            label = {
                'sequence': 1,
                'total': 1,
                'pack_text': '1 of 1',
                'po_number': po_number,
                'quantity': float(line_selection.selected_quantity),
                'grn_date': grn_date,
                'grn_number': doc_number,
                'expiration_date': 'N/A',
                'item_code': line_selection.item_code,
                'item_name': line_selection.item_description or '',
                'doc_number': doc_number,
                'bin_location': line_selection.bin_location or 'N/A',
                'qr_code_image': qr_code_image,
                'qr_data': qr_data
            }
            labels.append(label)
        
        logging.info(f"✅ Successfully generated {len(labels)} label(s) for line_selection_id={line_selection_id}, label_type={label_type}")
        
        return jsonify({
            'success': True,
            'labels': labels,
            'batch_id': batch_id,
            'line_selection_id': line_selection_id,
            'label_type': label_type,
            'total_labels': len(labels)
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f'Invalid value: {str(e)}'
        }), 400
    except Exception as e:
        logging.error(f"Error generating barcode labels: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@multi_grn_bp.route('/validate-item/<string:item_code>', methods=['GET'])
@login_required
def validate_item_code(item_code):
    """Validate ItemCode and return batch/serial requirements (reuses SAP validation)"""
    try:
        from sap_integration import SAPIntegration
        
        sap = SAPIntegration()
        validation_result = sap.validate_item_code(item_code)
        
        logging.info(f"🔍 Multi GRN ItemCode validation for {item_code}: {validation_result}")
        
        return jsonify(validation_result)
        
    except Exception as e:
        logging.error(f"Error validating ItemCode {item_code}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'item_code': item_code,
            'batch_required': False,
            'serial_required': False,
            'manage_method': 'N'
        }), 500

@multi_grn_bp.route('/batch/<int:batch_id>/add-item', methods=['POST'])
@login_required
def add_item_to_batch(batch_id):
    """Add item to Multi GRN batch with batch/serial details and number of bags support"""
    from modules.multi_grn_creation.models import MultiGRNBatchDetails, MultiGRNSerialDetails
    from sap_integration import SAPIntegration
    
    try:
        batch = MultiGRNBatch.query.get_or_404(batch_id)
        
        # Verify ownership
        if batch.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        if batch.status != 'draft':
            return jsonify({'success': False, 'error': 'Cannot add items to non-draft batch'}), 400
        
        # Get form data
        item_code = request.form.get('item_code')
        item_name = request.form.get('item_name')
        quantity = float(request.form.get('quantity', 0))
        unit_of_measure = request.form.get('unit_of_measure')
        warehouse_code = request.form.get('warehouse_code')
        bin_location = request.form.get('bin_location')
        batch_number = request.form.get('batch_number')
        expiry_date = request.form.get('expiry_date')
        serial_numbers_json = request.form.get('serial_numbers_json', '')
        batch_numbers_json = request.form.get('batch_numbers_json', '')
        number_of_bags = int(request.form.get('number_of_bags', 1))
        po_link_id = request.form.get('po_link_id')  # Optional: if adding from PO line
        po_line_num = request.form.get('po_line_num', -1)  # -1 for manual items
        
        if not all([item_code, item_name, quantity > 0]):
            return jsonify({'success': False, 'error': 'Item Code, Item Name, and Quantity are required'}), 400
        
        # Validate item code with SAP
        sap = SAPIntegration()
        validation_result = sap.validate_item_code(item_code)
        
        # FIX: Use correct field names from SAP validation response
        is_batch_managed = validation_result.get('batch_managed', False)
        is_serial_managed = validation_result.get('serial_managed', False)
        management_method = validation_result.get('management_method', 'A')
        
        logging.info(f"🔍 Item {item_code} validation: Batch={is_batch_managed}, Serial={is_serial_managed}, Method={management_method}")
        
        # Block serial-managed items (UI not implemented yet)
        if is_serial_managed:
            return jsonify({
                'success': False,
                'error': 'Serial-managed items are not currently supported in Multi GRN. Please use standard GRPO for serial items.'
            }), 400
        
        # Parse expiry date if provided
        expiry_date_obj = None
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid expiry date format. Use YYYY-MM-DD'}), 400
        
        # Create line selection with correct SAP-validated management fields
        line_selection = MultiGRNLineSelection(
            po_link_id=int(po_link_id) if po_link_id else batch.po_links[0].id,
            po_line_num=int(po_line_num),
            item_code=item_code,
            item_description=item_name,
            ordered_quantity=Decimal(str(quantity)),
            open_quantity=Decimal(str(quantity)),
            selected_quantity=Decimal(str(quantity)),
            warehouse_code=warehouse_code,
            bin_location=bin_location,
            unit_of_measure=unit_of_measure,
            line_status='manual' if int(po_line_num) == -1 else 'po_based',
            batch_required='Y' if is_batch_managed else 'N',
            serial_required='Y' if is_serial_managed else 'N',
            manage_method=management_method  # Use actual SAP management method ('A' or 'R')
        )
        
        db.session.add(line_selection)
        db.session.flush()
        
        # Handle serial numbers
        if is_serial_managed and serial_numbers_json:
            try:
                serial_numbers = json.loads(serial_numbers_json)
                
                if len(serial_numbers) != int(quantity):
                    db.session.rollback()
                    return jsonify({'success': False, 'error': f'Serial managed item requires {int(quantity)} serial numbers'}), 400
                
                # Validate bags can evenly divide serials
                if len(serial_numbers) % number_of_bags != 0:
                    db.session.rollback()
                    return jsonify({'success': False, 'error': f'Number of serials must be evenly divisible by number of bags'}), 400
                
                qty_per_pack = len(serial_numbers) / number_of_bags
                
                for idx, serial_data in enumerate(serial_numbers):
                    # Generate unique GRN number
                    grn_number = f"MGN-{batch.id}-{line_selection.id}-{idx+1}"
                    
                    serial = MultiGRNSerialDetails(
                        line_selection_id=line_selection.id,
                        serial_number=serial_data.get('internal_serial_number'),
                        manufacturer_serial_number=serial_data.get('manufacturer_serial_number', ''),
                        internal_serial_number=serial_data.get('internal_serial_number'),
                        expiry_date=datetime.strptime(serial_data['expiry_date'], '%Y-%m-%d').date() if serial_data.get('expiry_date') else None,
                        grn_number=grn_number,
                        qty_per_pack=qty_per_pack,
                        no_of_packs=number_of_bags
                    )
                    db.session.add(serial)
                
                logging.info(f"✅ Added {len(serial_numbers)} serial numbers for item {item_code}")
                
            except json.JSONDecodeError:
                db.session.rollback()
                return jsonify({'success': False, 'error': 'Invalid serial numbers data format'}), 400
        
        # Handle batch numbers
        if is_batch_managed and (batch_numbers_json or batch_number):
            try:
                # Handle simple batch number input or structured JSON
                if batch_numbers_json:
                    batch_numbers = json.loads(batch_numbers_json)
                elif batch_number:
                    # Create simple batch structure from single batch number
                    batch_numbers = [{
                        'batch_number': batch_number,
                        'quantity': quantity,
                        'expiry_date': expiry_date
                    }]
                else:
                    batch_numbers = []
                
                if batch_numbers:
                    total_batch_qty = sum(float(b.get('quantity', 0)) for b in batch_numbers)
                    if abs(total_batch_qty - quantity) > 0.001:
                        db.session.rollback()
                        return jsonify({'success': False, 'error': f'Total batch quantity must equal item quantity'}), 400
                    
                    import io
                    import base64
                    import qrcode
                    
                    total_labels_created = 0
                    
                    # Get PO number and GRN date for QR code data
                    po_number = line_selection.po_link.po_doc_num if line_selection.po_link else 'N/A'
                    grn_date = batch.created_at.strftime('%Y-%m-%d') if batch.created_at else datetime.now().strftime('%Y-%m-%d')
                    
                    for idx, batch_data in enumerate(batch_numbers):
                        batch_qty = float(batch_data.get('quantity', 0))
                        batch_qty_decimal = Decimal(str(batch_qty))
                        batch_qty_int = int(batch_qty_decimal.to_integral_value(rounding=ROUND_HALF_UP))
                        
                        # Create ONE batch_detail record with total quantity for this batch
                        batch_expiry = datetime.strptime(batch_data['expiry_date'], '%Y-%m-%d').date() if batch_data.get('expiry_date') else expiry_date_obj
                        batch_detail = MultiGRNBatchDetails(
                            line_selection_id=line_selection.id,
                            batch_number=batch_data.get('batch_number'),
                            quantity=Decimal(str(batch_qty_int)),
                            manufacturer_serial_number=batch_data.get('manufacturer_serial_number', ''),
                            internal_serial_number=batch_data.get('internal_serial_number', ''),
                            expiry_date=batch_expiry,
                            grn_number=f"MGN-{batch.id}-{line_selection.id}-{idx+1}",
                            qty_per_pack=Decimal(str(batch_qty_int)) / number_of_bags,
                            no_of_packs=number_of_bags
                        )
                        db.session.add(batch_detail)
                        db.session.flush()
                        
                        # Create label records for each pack
                        if number_of_bags > 1:
                            pack_quantities = distribute_quantity_to_packs(batch_qty_int, number_of_bags)
                            for pack_num in range(1, number_of_bags + 1):
                                pack_qty = pack_quantities[pack_num - 1]
                                grn_number = f"MGN-{batch.id}-{line_selection.id}-{idx+1}-{pack_num}"
                                
                                # Generate QR barcode for this pack with complete data
                                qr_data = {
                                    'id': grn_number,
                                    'po': str(po_number),
                                    'item': item_code,
                                    'batch': batch_data.get('batch_number'),
                                    'qty': pack_qty,
                                    'pack': f"{pack_num} of {number_of_bags}",
                                    'grn_date': grn_date,
                                    'exp_date': batch_expiry.strftime('%Y-%m-%d') if batch_expiry else 'N/A',
                                    'bin': line_selection.bin_location or 'N/A'
                                }
                                qr_text = json.dumps(qr_data)
                                
                                try:
                                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                                    qr.add_data(qr_text)
                                    qr.make(fit=True)
                                    img = qr.make_image(fill_color="black", back_color="white")
                                    buffer = io.BytesIO()
                                    img.save(buffer, format='PNG')
                                    buffer.seek(0)
                                    barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
                                except Exception as e:
                                    logging.error(f"Error generating QR code: {str(e)}")
                                    barcode = None
                                
                                label = MultiGRNBatchDetailsLabel(
                                    batch_detail_id=batch_detail.id,
                                    pack_number=pack_num,
                                    qty_in_pack=pack_qty,
                                    grn_number=grn_number,
                                    barcode=barcode,
                                    qr_data=qr_text
                                )
                                db.session.add(label)
                                total_labels_created += 1
                                logging.info(f"✅ Created pack label {pack_num}/{number_of_bags}: GRN={grn_number}, Qty={pack_qty}")
                        else:
                            # Single pack - create one label with complete data
                            grn_number = f"MGN-{batch.id}-{line_selection.id}-{idx+1}-1"
                            qr_data = {
                                'id': grn_number,
                                'po': str(po_number),
                                'item': item_code,
                                'batch': batch_data.get('batch_number'),
                                'qty': batch_qty_int,
                                'pack': f"1 of 1",
                                'grn_date': grn_date,
                                'exp_date': batch_expiry.strftime('%Y-%m-%d') if batch_expiry else 'N/A',
                                'bin': line_selection.bin_location or 'N/A'
                            }
                            qr_text = json.dumps(qr_data)
                            
                            try:
                                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                                qr.add_data(qr_text)
                                qr.make(fit=True)
                                img = qr.make_image(fill_color="black", back_color="white")
                                buffer = io.BytesIO()
                                img.save(buffer, format='PNG')
                                buffer.seek(0)
                                barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
                            except Exception as e:
                                logging.error(f"Error generating QR code: {str(e)}")
                                barcode = None
                            
                            label = MultiGRNBatchDetailsLabel(
                                batch_detail_id=batch_detail.id,
                                pack_number=1,
                                qty_in_pack=batch_qty_int,
                                grn_number=grn_number,
                                barcode=barcode,
                                qr_data=qr_text
                            )
                            db.session.add(label)
                            total_labels_created += 1
                    
                    logging.info(f"✅ Added {len(batch_numbers)} batch_details + {total_labels_created} pack labels for item {item_code}")
                
            except json.JSONDecodeError:
                db.session.rollback()
                return jsonify({'success': False, 'error': 'Invalid batch numbers data format'}), 400
        
        # Handle non-managed items with bags
        if not is_batch_managed and not is_serial_managed and number_of_bags > 1:
            import io
            import base64
            import qrcode
            
            # Create ONE batch_detail + N labels
            quantity_decimal = Decimal(str(quantity))
            quantity_int = int(quantity_decimal.to_integral_value(rounding=ROUND_HALF_UP))
            
            # Get PO number and GRN date for QR code data
            po_number = line_selection.po_link.po_doc_num if line_selection.po_link else 'N/A'
            grn_date = batch.created_at.strftime('%Y-%m-%d') if batch.created_at else datetime.now().strftime('%Y-%m-%d')
            
            # Create ONE batch_detail record with total quantity
            batch_detail = MultiGRNBatchDetails(
                line_selection_id=line_selection.id,
                batch_number=batch_number or f"BATCH-{batch.id}-{line_selection.id}",
                quantity=Decimal(str(quantity_int)),
                expiry_date=expiry_date_obj,
                grn_number=f"MGN-{batch.id}-{line_selection.id}-1",
                qty_per_pack=Decimal(str(quantity_int)) / number_of_bags,
                no_of_packs=number_of_bags
            )
            db.session.add(batch_detail)
            db.session.flush()
            
            # Distribute quantity across packs using helper function
            pack_quantities = distribute_quantity_to_packs(quantity_int, number_of_bags)
            
            # Create label records for each pack
            for pack_num in range(1, number_of_bags + 1):
                pack_qty = pack_quantities[pack_num - 1]
                grn_number = f"MGN-{batch.id}-{line_selection.id}-1-{pack_num}"
                
                # Generate QR barcode for this pack with complete data
                qr_data = {
                    'id': grn_number,
                    'po': str(po_number),
                    'item': item_code,
                    'batch': batch_number or f"BATCH-{batch.id}-{line_selection.id}",
                    'qty': pack_qty,
                    'pack': f"{pack_num} of {number_of_bags}",
                    'grn_date': grn_date,
                    'exp_date': expiry_date_obj.strftime('%Y-%m-%d') if expiry_date_obj else 'N/A',
                    'bin': bin_location or 'N/A'
                }
                qr_text = json.dumps(qr_data)
                
                try:
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                    qr.add_data(qr_text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    buffer.seek(0)
                    barcode = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
                except Exception as e:
                    logging.error(f"Error generating QR code: {str(e)}")
                    barcode = None
                
                # Create label record
                label = MultiGRNBatchDetailsLabel(
                    batch_detail_id=batch_detail.id,
                    pack_number=pack_num,
                    qty_in_pack=pack_qty,
                    grn_number=grn_number,
                    barcode=barcode,
                    qr_data=qr_text
                )
                db.session.add(label)
                logging.info(f"✅ Created pack label {pack_num}/{number_of_bags}: GRN={grn_number}, Qty={pack_qty}")
            
            logging.info(f"✅ Created 1 batch_detail + {number_of_bags} pack labels for non-managed item {item_code}: Total Qty={quantity_int}")
        
        db.session.commit()
        
        flash(f'Item {item_code} added successfully with {number_of_bags} bag(s)', 'success')
        return jsonify({
            'success': True,
            'message': f'Item {item_code} added successfully',
            'line_selection_id': line_selection.id,
            'number_of_bags': number_of_bags
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding item to batch: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@multi_grn_bp.route('/api/get-bins', methods=['GET'])
@login_required
def get_bin_locations():
    """Get bin locations for a specific warehouse"""
    try:
        warehouse_code = request.args.get('warehouse')
        if not warehouse_code:
            return jsonify({'success': False, 'error': 'Warehouse code required'}), 400
        
        from sap_integration import SAPIntegration
        sap = SAPIntegration()
        result = sap.get_bin_locations_list(warehouse_code)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify({'success': True, 'bins': []})
            
    except Exception as e:
        logging.error(f"Error getting bin locations: {str(e)}")
        return jsonify({'success': True, 'bins': []})
