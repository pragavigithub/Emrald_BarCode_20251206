"""
Routes for SO Against Invoice Module
Implements the complete workflow for creating invoices against Sales Orders
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
# from flask_wtf.csrf import validate_csrf  # Disabled per user request
from datetime import datetime, timedelta
import logging
import json
import os

from app import app, db
from models import User, DocumentNumberSeries
from .models import SOInvoiceDocument, SOInvoiceItem, SOInvoiceSerial, SOSeries
from sap_integration import SAPIntegration

# Create blueprint for SO Against Invoice module
so_invoice_bp = Blueprint('so_against_invoice', __name__, template_folder='templates', url_prefix='/so-against-invoice')


def generate_so_invoice_number():
    """Generate unique document number for SO Against Invoice"""
    return DocumentNumberSeries.get_next_number('SO_AGAINST_INVOICE')


def is_production_environment():
    """Check if running in production environment"""
    return not (app.debug or os.environ.get('FLASK_ENV') == 'development')


def validate_json_csrf():
    """CSRF validation disabled per user request"""
    # CSRF protection has been disabled globally - always return True
    return True


@so_invoice_bp.route('/', methods=['GET'])
@login_required
def index():
    """SO Against Invoice main page with document listing"""
    if not current_user.has_permission('so_against_invoice'):
        flash('Access denied - SO Against Invoice permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search = request.args.get('search', '', type=str)
        user_based = request.args.get('user_based', 'true', type=str)
        
        # Ensure per_page is within allowed range
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
        
        # Build base query
        query = SOInvoiceDocument.query
        
        # Apply user-based filtering
        if current_user.role in ['admin', 'manager']:
            # Admin/Manager can see all or filter by user preference
            if user_based == 'true':
                query = query.filter_by(user_id=current_user.id)
        else:
            # Non-admin users only see their own documents
            query = query.filter_by(user_id=current_user.id)
        
        # Apply search filter if provided
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                db.or_(
                    SOInvoiceDocument.document_number.ilike(search_filter),
                    SOInvoiceDocument.so_number.ilike(search_filter),
                    SOInvoiceDocument.card_code.ilike(search_filter),
                    SOInvoiceDocument.card_name.ilike(search_filter),
                    SOInvoiceDocument.status.ilike(search_filter)
                )
            )
        
        # Order and paginate
        query = query.order_by(SOInvoiceDocument.created_at.desc())
        documents_paginated = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('so_against_invoice/index.html',
                             documents=documents_paginated.items,
                             pagination=documents_paginated,
                             search=search,
                             per_page=per_page,
                             user_based=user_based,
                             current_user=current_user)
    
    except Exception as e:
        logging.error(f"Error in SO Against Invoice index: {str(e)}")
        flash(f'Error loading documents: {str(e)}', 'error')
        return render_template('so_against_invoice/index.html',
                             documents=[],
                             pagination=None,
                             search='',
                             per_page=10,
                             user_based='true',
                             current_user=current_user)


@so_invoice_bp.route('/cleanup_empty_drafts', methods=['POST'])
@login_required
def cleanup_empty_drafts():
    """Clean up empty draft SO Against Invoice documents that have no line items"""
    try:
        if not current_user.has_permission('so_against_invoice'):
            flash('Access denied - SO Against Invoice permissions required', 'error')
            return redirect(url_for('so_against_invoice.index'))

        # Find all draft documents by this user that have no items
        empty_drafts = db.session.query(SOInvoiceDocument).filter(
            SOInvoiceDocument.user_id == current_user.id,
            SOInvoiceDocument.status == 'draft',
            ~SOInvoiceDocument.items.any()  # No line items
        ).all()

        count = 0
        for draft in empty_drafts:
            db.session.delete(draft)
            count += 1

        db.session.commit()

        logging.info(f"✅ Cleaned up {count} empty draft SO Against Invoice documents for user {current_user.username}")

        if count > 0:
            flash(f'✅ Successfully cleaned up {count} empty draft documents', 'success')
        else:
            flash('No empty draft documents found to clean up', 'info')
        
        return redirect(url_for('so_against_invoice.index'))

    except Exception as e:
        db.session.rollback()
        logging.error(f"❌ Error cleaning up empty drafts: {str(e)}")
        flash(f'Error cleaning up empty drafts: {str(e)}', 'error')
        return redirect(url_for('so_against_invoice.index'))


@so_invoice_bp.route('/create', methods=['POST'])
@login_required 
def create():
    """Create new SO Against Invoice document - Skip process flow screen"""
    if not current_user.has_permission('so_against_invoice'):
        flash('Access denied - SO Against Invoice permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Generate document number immediately and create the document
        document_number = generate_so_invoice_number()
        
        # Create new document
        document = SOInvoiceDocument(
            document_number=document_number,
            user_id=current_user.id,
            comments="SO Against Invoice - Created via WMS"
        )
        
        db.session.add(document)
        db.session.commit()
        
        flash(f'SO Against Invoice {document_number} created successfully', 'success')
        # Skip the process flow screen and go directly to detail page
        return redirect(url_for('so_against_invoice.detail', doc_id=document.id))
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating SO Against Invoice: {str(e)}")
        flash(f'Error creating document: {str(e)}', 'error')
        return redirect(url_for('so_against_invoice.index'))


@so_invoice_bp.route('/detail/<int:doc_id>')
@login_required
def detail(doc_id):
    """SO Against Invoice detail page"""
    if not current_user.has_permission('so_against_invoice'):
        flash('Access denied - SO Against Invoice permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        document = SOInvoiceDocument.query.get_or_404(doc_id)
        
        # Check permissions
        if current_user.role not in ['admin', 'manager'] and document.user_id != current_user.id:
            flash('Access denied - You can only view your own documents', 'error')
            return redirect(url_for('so_against_invoice.index'))
        
        return render_template('so_against_invoice/detail.html', 
                             document=document,
                             current_user=current_user)
    
    except Exception as e:
        logging.error(f"Error loading SO Against Invoice detail: {str(e)}")
        flash(f'Error loading document: {str(e)}', 'error')
        return redirect(url_for('so_against_invoice.index'))


# Step 1: Get Sales Order Series API
@so_invoice_bp.route('/api/get-so-series', methods=['GET'])
@login_required
def get_so_series():
    """Get available SO Series from SAP B1"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        sap = SAPIntegration()
        
        # Try to get series from SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/SQLQueries('Get_SO_Series')/List"
                response = sap.session.post(url, json={}, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    series_list = data.get('value', [])
                    
                    # Cache series in database for faster lookup
                    for series_data in series_list:
                        existing_series = SOSeries.query.filter_by(series=series_data['Series']).first()
                        if not existing_series:
                            new_series = SOSeries(
                                series=series_data['Series'],
                                series_name=series_data['SeriesName']
                            )
                            db.session.add(new_series)
                    
                    db.session.commit()
                    logging.info(f"Retrieved {len(series_list)} SO series from SAP B1")
                    
                    return jsonify({
                        'success': True,
                        'series': series_list
                    })
                    
            except Exception as e:
                logging.error(f"Error getting SO series from SAP: {str(e)}")
        
        # Fallback to cached data or mock data
        cached_series = SOSeries.query.all()
        if cached_series:
            series_list = [{'Series': s.series, 'SeriesName': s.series_name} for s in cached_series]
            return jsonify({
                'success': True,
                'series': series_list
            })
        
        # Return error in production if no cached data available
        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable and no cached series data found'
            }), 503
        
        # Return minimal mock data for development only
        return jsonify({
            'success': True,
            'series': [

            ],
            'development_mode': True
        })
    
    except Exception as e:
        logging.error(f"Error in get_so_series API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Step 2: Validate SO Number with Series
@so_invoice_bp.route('/api/validate-so-number', methods=['POST'])
@login_required
def validate_so_number():
    """Validate SO Number with Series and get DocEntry"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        so_number = data.get('so_number')
        series = data.get('series')
        
        if not so_number or not series:
            return jsonify({
                'success': False,
                'error': 'SO Number and Series are required'
            }), 400
        
        sap = SAPIntegration()
        
        # Try to validate with SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/SQLQueries('Get_SO_Details')/List"
                request_body = {
                    "ParamList": f"SONumber='{so_number}'&Series='{series}'"
                }
                response = sap.session.post(url, json=request_body, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    so_details = data.get('value', [])
                    
                    if so_details:
                        doc_entry = so_details[0].get('DocEntry')
                        return jsonify({
                            'success': True,
                            'doc_entry': doc_entry,
                            'message': f'SO {so_number} validated successfully'
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'SO Number {so_number} not found in Series {series}'
                        }), 404
                        
            except Exception as e:
                logging.error(f"Error validating SO with SAP: {str(e)}")
        
        # Strict production check - never allow mock validation in production
        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot validate SO numbers in production without live connection'
            }), 503
        
        # Development mode only - with clear warnings
        logging.warning(f"DEVELOPMENT MODE: Mock validation for SO {so_number}")
        return jsonify({
            'success': True,
            'doc_entry': 1248,
            'development_mode': True,
            'warning': 'This is a development mode response - not validated against real data',
            'message': f'SO {so_number} mock validation (DEVELOPMENT ONLY)'
        })
    
    except Exception as e:
        logging.error(f"Error in validate_so_number API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Step 3: Fetch Sales Order Details
# @so_invoice_bp.route('/api/fetch-so-details', methods=['POST'])
# @login_required
# def fetch_so_details():
#     """Fetch full SO details using DocEntry"""
#     if not current_user.has_permission('so_against_invoice'):
#         return jsonify({
#             'success': False,
#             'error': 'Access denied - SO Against Invoice permissions required'
#         }), 403
#
#     try:
#         # Validate CSRF token for JSON requests
#         if not validate_json_csrf():
#             return jsonify({
#                 'success': False,
#                 'error': 'CSRF validation failed'
#             }), 403
#         data = request.get_json()
#         doc_entry = data.get('doc_entry')
#
#         if not doc_entry:
#             return jsonify({
#                 'success': False,
#                 'error': 'DocEntry is required'
#             }), 400
#
#         sap = SAPIntegration()
#
#         # Try to fetch from SAP B1
#         if sap.ensure_logged_in():
#             try:
#                 url = f"{sap.base_url}/b1s/v1/Orders?$filter=DocEntry eq {doc_entry}"
#                 response = sap.session.get(url, timeout=10)
#
#                 if response.status_code == 200:
#                     data = response.json()
#                     orders = data.get('value', [])
#
#                     if orders:
#                         order = orders[0]
#                         return jsonify({
#                             'success': True,
#                             'order': order
#                         })
#                     else:
#                         return jsonify({
#                             'success': False,
#                             'error': f'SO with DocEntry {doc_entry} not found'
#                         }), 404
#
#             except Exception as e:
#                 logging.error(f"Error fetching SO details from SAP: {str(e)}")
#
#         # Strict production check - never return empty mock orders in production
#         if is_production_environment():
#             return jsonify({
#                 'success': False,
#                 'error': 'SAP B1 service unavailable - cannot fetch SO details in production without live connection'
#             }), 503
#
#         # Development mode only - return structured mock data
#         mock_order = {
#
#         }
#
#         logging.warning(f"DEVELOPMENT MODE: Mock SO data for DocEntry {doc_entry}")
#         return jsonify({
#             'success': True,
#             'order': mock_order,
#             'development_mode': True,
#             'warning': 'This is development mode mock data - not real SAP data'
#         })
#
#     except Exception as e:
#         logging.error(f"Error in fetch_so_details API: {str(e)}")
#         return jsonify({
#             'success': False,
#             'error': str(e)
#         }), 500
#
# Step 3: Fetch Sales Order Details
@so_invoice_bp.route('/api/fetch-so-details', methods=['POST'])
@login_required
def fetch_so_details():
    """Fetch full SO details using DocEntry, filter open documents and lines"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403

    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403

        data = request.get_json()
        doc_entry = data.get('doc_entry')

        if not doc_entry:
            return jsonify({
                'success': False,
                'error': 'DocEntry is required'
            }), 400

        sap = SAPIntegration()

        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/Orders?$filter=DocEntry eq {doc_entry}"
                response = sap.session.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    orders = data.get('value', [])

                    if orders:
                        order = orders[0]

                        # ✅ Check DocumentStatus
                        if order.get("DocumentStatus") != "bost_Open":
                            return jsonify({
                                'success': False,
                                'error': f"SO {doc_entry} is already closed"
                            }), 400

                        # ✅ Filter only open lines
                        open_lines = [
                            line for line in order.get("DocumentLines", [])
                            if line.get("LineStatus") == "bost_Open"
                        ]
                        order["DocumentLines"] = open_lines

                        return jsonify({
                            'success': True,
                            'order': order
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'SO with DocEntry {doc_entry} not found'
                        }), 404

            except Exception as e:
                logging.error(f"Error fetching SO details from SAP: {str(e)}")

        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot fetch SO details in production without live connection'
            }), 503

        # Dev mode mock
        mock_order = {}
        logging.warning(f"DEVELOPMENT MODE: Mock SO data for DocEntry {doc_entry}")
        return jsonify({
            'success': True,
            'order': mock_order,
            'development_mode': True,
            'warning': 'This is development mode mock data - not real SAP data'
        })

    except Exception as e:
        logging.error(f"Error in fetch_so_details API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Step 4: Validation Rules for Serial and Non-Serial Items
@so_invoice_bp.route('/api/validate-item', methods=['POST'])
@login_required
def validate_item():
    """Validate item details (Serial Number or Quantity)"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        item_code = data.get('item_code')
        warehouse_code = data.get('warehouse_code')
        serial_number = data.get('serial_number')
        quantity = data.get('quantity', 1)
        item_type = data.get('item_type', 'serial')  # 'serial' or 'non_serial'
        
        if not item_code or not warehouse_code:
            return jsonify({
                'success': False,
                'error': 'ItemCode and WarehouseCode are required'
            }), 400
        
        sap = SAPIntegration()
        
        if item_type == 'serial' and serial_number:
            # Scenario 1: Serial Number Managed Items
            if sap.ensure_logged_in():
                try:
                    url = f"{sap.base_url}/b1s/v1/SQLQueries('Series_Validation')/List"
                    request_body = {
                        "ParamList": f"whsCode='{warehouse_code}'&itemCode='{item_code}'&series='{serial_number}'"
                    }
                    response = sap.session.post(url, json=request_body, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        serial_details = data.get('value', [])
                        
                        if serial_details:
                            serial_info = serial_details[0]
                            return jsonify({
                                'success': True,
                                'validated': True,
                                'item_type': 'serial',
                                'serial_info': serial_info,
                                'message': f'Serial {serial_number} validated successfully'
                            })
                        else:
                            return jsonify({
                                'success': False,
                                'error': f'Serial {serial_number} not found for item {item_code} in warehouse {warehouse_code}'
                            })
                            
                except Exception as e:
                    logging.error(f"Error validating serial with SAP: {str(e)}")
            
            # Strict production check for serial validation
            if is_production_environment():
                return jsonify({
                    'success': False,
                    'error': 'SAP B1 service unavailable - cannot validate serial numbers in production without live connection'
                }), 503
            
            # Development mode only - with clear warnings
            logging.warning(f"DEVELOPMENT MODE: Mock serial validation for {serial_number}")
            return jsonify({
                'success': True,
                'validated': True,
                'item_type': 'serial',
                'serial_info': {
                    'DistNumber': serial_number,
                    'ItemCode': item_code,
                    'WhsCode': warehouse_code
                },
                'development_mode': True,
                'warning': 'Development mode - serial not validated against real data',
                'message': f'Serial {serial_number} mock validation (DEVELOPMENT ONLY)'
            })
        
        elif item_type == 'non_serial':
            # Scenario 2: Non-Serial Items - validate quantity against available stock
            if sap.ensure_logged_in():
                try:
                    # Use proper Quantity_Check SAP API
                    url = f"{sap.base_url}/b1s/v1/SQLQueries('Quantity_Check')/List"
                    request_body = {
                        "ParamList": f"whCode='{warehouse_code}'&itemCode='{item_code}'"
                    }
                    response = sap.session.post(url, json=request_body, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        stock_info = data.get('value', [])
                        
                        if stock_info:
                            available_qty = stock_info[0].get('OnHand', 0)
                            if quantity <= available_qty:
                                return jsonify({
                                    'success': True,
                                    'validated': True,
                                    'item_type': 'non_serial',
                                    'quantity': quantity,
                                    'available_qty': available_qty,
                                    'message': f'Quantity {quantity} validated for item {item_code}'
                                })
                            else:
                                return jsonify({
                                    'success': False,
                                    'error': f'Insufficient stock. Available: {available_qty}, Requested: {quantity}'
                                }), 400
                        else:
                            return jsonify({
                                'success': False,
                                'error': f'No stock information found for item {item_code}'
                            }), 404
                            
                except Exception as e:
                    logging.error(f"Error checking stock with SAP: {str(e)}")
            
            # Production environment - require SAP connection
            if is_production_environment():
                return jsonify({
                    'success': False,
                    'error': 'SAP B1 service unavailable - cannot validate non-serial items in production'
                }), 503
            
            # Development mode fallback
            logging.warning(f"DEVELOPMENT MODE: Mock quantity validation for {item_code}")
            return jsonify({
                'success': True,
                'validated': True,
                'item_type': 'non_serial',
                'quantity': quantity,
                'available_qty': 999,  # Mock high availability
                'development_mode': True,
                'warning': 'Development mode - quantity not validated against real stock',
                'message': f'Quantity {quantity} mock validation for item {item_code} (DEVELOPMENT ONLY)'
            })
        
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid item type or missing required fields'
            }), 400
    
    except Exception as e:
        logging.error(f"Error in validate_item API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Step 5: Post Invoice to SAP B1
@so_invoice_bp.route('/api/post-invoice', methods=['POST'])
@login_required
def post_invoice():
    """Post validated invoice to SAP B1"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        doc_id = data.get('doc_id')
        
        if not doc_id:
            return jsonify({
                'success': False,
                'error': 'Document ID is required'
            }), 400
        
        document = SOInvoiceDocument.query.get_or_404(doc_id)

        # Check permissions
        if current_user.role not in ['admin', 'manager'] and document.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Access denied'
            }), 403
        
        # Validate document has items
        if not document.items:
            return jsonify({
                'success': False,
                'error': 'Cannot post invoice without line items'
            }), 400
        sap = SAPIntegration()
        # Build invoice request for SAP B1
        #bplId = sap.get_warehouse_business_place_id(item.warehouse_code)
        invoice_data = {
            "DocDate": document.doc_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "DocDueDate": (document.doc_due_date or document.doc_date + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "BPL_IDAssignedToInvoice": document.bplid,
            "CardCode": document.card_code,
            "U_EA_CREATEDBy": current_user.username,
            "U_EA_Approved": current_user.username,
            "Comments": f"SO Against Invoice - {document.document_number}",
            "DocumentLines": []
        }
        
        # Add line items
        for item in document.items:

            line_data = {
                "ItemCode": item.item_code,
                "ItemDescription": item.item_description,
                "Quantity": item.validated_quantity,
                "WarehouseCode": item.warehouse_code
            }
            
            # Add serial numbers if any
            if item.serial_numbers:
                line_data["SerialNumbers"] = []
                for serial in item.serial_numbers:
                    line_data["SerialNumbers"].append({
                        "InternalSerialNumber": serial.serial_number,
                        "Quantity": serial.quantity,
                        "BaseLineNumber": serial.base_line_number
                    })
            
            invoice_data["DocumentLines"].append(line_data)
        print(invoice_data)
        # Try to post to SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/Invoices"
                response = sap.session.post(url, json=invoice_data, timeout=30)
                
                if response.status_code in [200, 201]:
                    result_data = response.json()
                    sap_doc_num = result_data.get('DocNum')
                    
                    # Update document with SAP details
                    document.sap_invoice_number = str(sap_doc_num)
                    document.status = 'posted'
                    document.updated_at = datetime.utcnow()
                    
                    db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'sap_doc_num': sap_doc_num,
                        'message': f'Invoice posted successfully to SAP B1. DocNum: {sap_doc_num}'
                    })
                else:
                    error_msg = f"SAP B1 error: {response.status_code} - {response.text}"
                    document.posting_error = error_msg
                    document.status = 'failed'
                    db.session.commit()
                    
                    return jsonify({
                        'success': False,
                        'error': error_msg
                    }), 400
                    
            except Exception as e:
                error_msg = f"Error posting to SAP B1: {str(e)}"
                document.posting_error = error_msg
                document.status = 'failed'
                db.session.commit()
                
                logging.error(error_msg)
                return jsonify({
                    'success': False,
                    'error': error_msg
                }), 500
        
        # CRITICAL: Never allow fake posting in production
        if is_production_environment():
            document.posting_error = "SAP B1 service unavailable - invoice posting failed"
            document.status = 'failed'
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot post invoices in production without live connection',
                'critical_error': True
            }), 503
        
        # Development mode only - with clear simulation markers
        document.sap_invoice_number = f"DEV-INV{document.id:06d}"
        document.status = 'posted'
        document.updated_at = datetime.utcnow()
        db.session.commit()
        
        logging.warning(f"DEVELOPMENT MODE: Simulated invoice posting for document {document.id}")
        return jsonify({
            'success': True,
            'sap_doc_num': document.sap_invoice_number,
            'development_mode': True,
            'warning': 'SIMULATED POSTING - This invoice was NOT posted to real SAP system',
            'message': f'Invoice simulated successfully (DEVELOPMENT ONLY). DocNum: {document.sap_invoice_number}'
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in post_invoice API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@so_invoice_bp.route('/api/save-so-details', methods=['POST'])
@login_required
def save_so_details():
    """Save SO details to document after validation"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        doc_id = data.get('doc_id')
        so_details = data.get('so_details')
        series_info = data.get('series_info')
        
        if not doc_id or not so_details or not series_info:
            return jsonify({
                'success': False,
                'error': 'Missing required data'
            }), 400
        
        document = SOInvoiceDocument.query.get_or_404(doc_id)
        
        # Update document with SO details
        document.so_series = series_info.get('series')
        document.so_series_name = series_info.get('series_name')
        document.so_number = so_details.get('so_number')
        document.so_doc_entry = so_details.get('doc_entry')
        document.userSign=so_details.get('order',{}).get('UserSign')
        document.bplid=so_details.get('order',{}).get('BPL_IDAssignedToInvoice')
        document.card_code = so_details.get('order', {}).get('CardCode')
        document.card_name = so_details.get('order', {}).get('CardName')
        document.customer_address = so_details.get('order', {}).get('Address')
        document.status = 'validated'
        
        # Clear existing items and add new ones from SO
        SOInvoiceItem.query.filter_by(so_invoice_id=doc_id).delete()
        
        order = so_details.get('order', {})
        document_lines = order.get('DocumentLines', [])
        
        for line in document_lines:
            item = SOInvoiceItem(
                so_invoice_id=doc_id,
                line_num=line.get('LineNum'),
                item_code=line.get('ItemCode'),
                item_description=line.get('ItemDescription'),
                so_quantity=line.get('Quantity'),
                warehouse_code=line.get('WarehouseCode'),
                validated_quantity=0  # Will be updated when items are validated
            )
            db.session.add(item)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'SO details saved successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error saving SO details: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Enhanced API Endpoints for Dual-Grid System

@so_invoice_bp.route('/api/check-item-stock', methods=['POST'])
@login_required
def check_item_stock():
    """Check item stock and management type using Quantity_Check API"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        item_code = data.get('item_code')
        warehouse_code = data.get('warehouse_code')
        
        if not item_code or not warehouse_code:
            return jsonify({
                'success': False,
                'error': 'ItemCode and WarehouseCode are required'
            }), 400
        
        sap = SAPIntegration()
        
        # Try to get stock info from SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/SQLQueries('Quantity_Check')/List"
                request_body = {
                    "ParamList": f"whCode='{warehouse_code}'&itemCode='{item_code}'"
                }
                response = sap.session.post(url, json=request_body, timeout=10)
                
                if response.status_code == 200:
                    response_data = response.json()
                    stock_info = response_data.get('value', [])
                    
                    if stock_info:
                        item_info = stock_info[0]
                        return jsonify({
                            'success': True,
                            'item_code': item_info.get('ItemCode'),
                            'man_ser_num': item_info.get('ManSerNum'),
                            'on_hand': item_info.get('OnHand', 0)
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'No stock information found for item {item_code} in warehouse {warehouse_code}'
                        })
                        
            except Exception as e:
                logging.error(f"Error checking stock with SAP: {str(e)}")
        
        # Production check for stock information
        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot check stock in production without live connection'
            }), 503
        
        # Development mode mock data
        logging.warning(f"DEVELOPMENT MODE: Mock stock check for {item_code}")
        return jsonify({
            'success': True,
            'item_code': item_code,
            'man_ser_num': 'Y' if 'serial' in item_code.lower() else 'N',
            'on_hand': 100,  # Mock available quantity
            'development_mode': True,
            'warning': 'Development mode - stock data is simulated'
        })
    
    except Exception as e:
        logging.error(f"Error in check_item_stock API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@so_invoice_bp.route('/api/validate-serial', methods=['POST'])
@login_required
def validate_serial():
    """Validate a single serial number"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        item_code = data.get('item_code')
        warehouse_code = data.get('warehouse_code')
        serial_number = data.get('serial_number')
        
        if not item_code or not warehouse_code or not serial_number:
            return jsonify({
                'success': False,
                'error': 'ItemCode, WarehouseCode, and SerialNumber are required'
            }), 400
        
        sap = SAPIntegration()
        
        # Try to validate with SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/SQLQueries('Series_Validation')/List"
                request_body = {
                    "ParamList": f"whsCode='{warehouse_code}'&itemCode='{item_code}'&series='{serial_number}'"
                }
                response = sap.session.post(url, json=request_body, timeout=10)
                
                if response.status_code == 200:
                    response_data = response.json()
                    serial_details = response_data.get('value', [])
                    
                    if serial_details:
                        return jsonify({
                            'success': True,
                            'serial_number': serial_number,
                            'message': f'Serial {serial_number} validated successfully'
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'Serial {serial_number} not found or not available'
                        })
                        
            except Exception as e:
                logging.error(f"Error validating serial with SAP: {str(e)}")
        
        # Production check for serial validation
        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot validate serials in production without live connection'
            }), 503
        
        # Development mode mock validation
        logging.warning(f"DEVELOPMENT MODE: Mock serial validation for {serial_number}")
        return jsonify({
            'success': True,
            'serial_number': serial_number,
            'development_mode': True,
            'warning': 'Development mode - serial not validated against real data',
            'message': f'Serial {serial_number} mock validation (DEVELOPMENT ONLY)'
        })
    
    except Exception as e:
        logging.error(f"Error in validate_serial API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@so_invoice_bp.route('/api/add-validated-item', methods=['POST'])
@login_required
def add_validated_item():
    """Add item to validated grid"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        item_id = data.get('item_id')
        # Fix 1: Cast to float to prevent string vs int comparison error
        try:
            validated_quantity = float(data.get('validated_quantity', 0))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid quantity format'
            }), 400
        serial_numbers = data.get('serial_numbers', [])
        
        if not item_id or validated_quantity <= 0:
            return jsonify({
                'success': False,
                'error': 'Item ID and valid quantity are required'
            }), 400
        
        # Get the item
        item = SOInvoiceItem.query.get_or_404(item_id)
        
        # Check permissions
        if current_user.role not in ['admin', 'manager'] and item.so_invoice.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Access denied'
            }), 403
        
        # Fix 2: Validate quantity against SO quantity
        if item.is_serial_managed:
            # For serial items, check number of serial numbers against SO quantity
            if len(serial_numbers) > item.so_quantity:
                return jsonify({
                    'success': False,
                    'error': f'Serial count ({len(serial_numbers)}) exceeds SO quantity ({item.so_quantity}). Maximum allowed: {int(item.so_quantity)}'
                }), 400
            # For serial items, validated quantity should match number of serials
            validated_quantity = float(len(serial_numbers))
        else:
            # For non-serial items, check validated quantity against SO quantity
            if validated_quantity > item.so_quantity:
                return jsonify({
                    'success': False,
                    'error': f'Validated quantity ({validated_quantity}) exceeds SO quantity ({item.so_quantity}). Maximum allowed: {item.so_quantity}'
                }), 400
        
        # Update validated quantity
        item.validated_quantity = validated_quantity
        item.validation_status = 'validated'
        item.validation_error = None
        
        # Clear existing serial numbers for this item
        SOInvoiceSerial.query.filter_by(so_invoice_item_id=item_id).delete()
        
        # Add serial numbers if provided
        if serial_numbers:
            for i, serial_number in enumerate(serial_numbers):
                serial_entry = SOInvoiceSerial(
                    so_invoice_item_id=item_id,
                    serial_number=serial_number,
                    quantity=1,
                    base_line_number=i + 1,
                    validation_status='validated'
                )
                db.session.add(serial_entry)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Item {item.item_code} added to validated grid with quantity {validated_quantity}'
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in add_validated_item API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@so_invoice_bp.route('/api/remove-validated-item', methods=['POST'])
@login_required
def remove_validated_item():
    """Remove item from validated grid"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        data = request.get_json()
        item_id = data.get('item_id')
        
        if not item_id:
            return jsonify({
                'success': False,
                'error': 'Item ID is required'
            }), 400
        
        # Get the item
        item = SOInvoiceItem.query.get_or_404(item_id)
        
        # Check permissions
        if current_user.role not in ['admin', 'manager'] and item.so_invoice.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Access denied'
            }), 403
        
        # Reset validated quantity and status
        item.validated_quantity = 0
        item.validation_status = 'pending'
        item.validation_error = None
        
        # Clear serial numbers
        SOInvoiceSerial.query.filter_by(so_invoice_item_id=item_id).delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Item {item.item_code} removed from validated grid'
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in remove_validated_item API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@so_invoice_bp.route('/api/post-invoice-to-sap', methods=['POST'])
@login_required
def post_invoice_to_sap():
    """Post validated line items to SAP B1 as Draft Invoice"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403

        data = request.get_json()
        doc_id = data.get('doc_id')
        
        if not doc_id:
            return jsonify({
                'success': False,
                'error': 'Document ID is required'
            }), 400

        document = SOInvoiceDocument.query.get_or_404(doc_id)
        
        # Check if document is ready for posting
        if document.status != 'validated':
            return jsonify({
                'success': False,
                'error': 'Document must be validated before posting'
            }), 400

        # Get validated items
        validated_items = SOInvoiceItem.query.filter(
            SOInvoiceItem.so_invoice_id == doc_id,
            SOInvoiceItem.validated_quantity > 0
        ).all()

        if not validated_items:
            return jsonify({
                'success': False,
                'error': 'No validated items found for posting'
            }), 400

        # Initialize SAP integration
        sap = SAPIntegration()
        
        if not sap.ensure_logged_in():
            return jsonify({
                'success': False,
                'error': 'Failed to connect to SAP B1'
            }), 503

        # Prepare document lines for SAP B1 Draft
        document_lines = []
        
        for idx, item in enumerate(validated_items):
            # Get serial numbers for this item
            serial_numbers = SOInvoiceSerial.query.filter_by(
                so_invoice_item_id=item.id,
                validation_status='validated'
            ).all()

            # Prepare line data
            line_data = {
                "LineNum": idx,
                "ItemCode": item.item_code,
                "ItemDescription": item.item_description,
                "Quantity": float(item.validated_quantity),
                "WarehouseCode": item.warehouse_code,
                "BaseType": 17,  # Sales Order
                "BaseEntry": document.so_doc_entry,
                "BaseLine": item.line_num
            }

            # Add serial numbers if item is serial managed
            if serial_numbers:
                line_data["SerialNumbers"] = [
                    {
                        "InternalSerialNumber": serial.serial_number,
                        "Quantity": 1.0
                    } for serial in serial_numbers
                ]
            
            document_lines.append(line_data)

        # Prepare the complete request body for SAP B1 Drafts
        request_body = {
            "DocObjectCode": "oInvoices",
            "DocType": "dDocument_Items",
            "DocDate": document.doc_date.strftime('%Y-%m-%d') if document.doc_date else datetime.utcnow().strftime('%Y-%m-%d'),
            "DocDueDate": document.doc_due_date.strftime('%Y-%m-%d') if document.doc_due_date else (datetime.utcnow().replace(month=12, day=14)).strftime('%Y-%m-%d'),
            "CardCode": document.card_code,
            "CardName": document.card_name,
            "Comments": f"Based On Sales Orders {document.so_number}.",
            "JournalMemo": f"A/R Invoices - {document.card_code}",
            "DocumentStatus": "bost_Open",
            "UserSign": document.userSign,
            "BPL_IDAssignedToInvoice": document.bplid,
            "AuthorizationStatus": "dasPending",
            "DocumentLines": document_lines
        }
        print(request_body)
        # Post to SAP B1 Drafts endpoint
        try:
            draft_url = f"{sap.base_url}/b1s/v1/Drafts"
            logging.info(f"Posting to SAP B1 Drafts endpoint: {draft_url}")
            logging.debug(f"Request body: {request_body}")
            
            response = sap.session.post(draft_url, json=request_body, timeout=30)
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                draft_doc_entry = response_data.get('DocEntry')
                draft_doc_num = response_data.get('DocNum', draft_doc_entry)
                
                # Update document status
                document.status = 'posted'
                document.sap_invoice_number = f"DRAFT-{draft_doc_num}"
                document.posting_error = None
                document.comments = f"Posted to SAP B1 as Draft {draft_doc_num} (DocEntry: {draft_doc_entry})"
                
                db.session.commit()
                
                logging.info(f"Successfully posted SO Invoice {document.document_number} to SAP B1 as Draft {draft_doc_num} (DocEntry: {draft_doc_entry})")
                
                return jsonify({
                    'success': True,
                    'message': f'Invoice posted to SAP B1 successfully as Draft {draft_doc_num}',
                    'draft_doc_entry': draft_doc_entry,
                    'sap_draft_number': f"DRAFT-{draft_doc_num}"
                })
            else:
                # Handle SAP B1 API error - sanitize error message
                error_message = f"SAP B1 API returned status {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data and 'message' in error_data['error']:
                        if 'value' in error_data['error']['message']:
                            error_message += f": {error_data['error']['message']['value']}"
                        else:
                            error_message += f": {error_data['error']['message']}"
                except:
                    error_message += ": Unable to parse error response"
                
                logging.error(f"SAP B1 posting failed: {error_message}. Response: {response.text[:500]}")
                
                document.status = 'failed'
                document.posting_error = error_message
                db.session.commit()
                
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 500
                
        except Exception as sap_error:
            # Sanitize error message for client
            error_message = "SAP B1 connection or posting error occurred"
            full_error = f"SAP B1 posting error: {str(sap_error)}"
            logging.error(full_error)
            
            document.status = 'failed'
            document.posting_error = full_error
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': error_message
            }), 500

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in post_invoice_to_sap API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Data Sync API for updating SO details from SAP B1
@so_invoice_bp.route('/api/sync-so-data', methods=['POST'])
@login_required
def sync_so_data():
    """Sync Sales Order data from SAP B1 to update document with latest changes"""
    if not current_user.has_permission('so_against_invoice'):
        return jsonify({
            'success': False,
            'error': 'Access denied - SO Against Invoice permissions required'
        }), 403
    
    try:
        # Validate CSRF token for JSON requests
        if not validate_json_csrf():
            return jsonify({
                'success': False,
                'error': 'CSRF validation failed'
            }), 403
        
        data = request.get_json()
        doc_id = data.get('doc_id')
        
        if not doc_id:
            return jsonify({
                'success': False,
                'error': 'Document ID is required'
            }), 400
        
        # Get the document
        document = SOInvoiceDocument.query.get_or_404(doc_id)
        
        # Check permissions
        if current_user.role not in ['admin', 'manager'] and document.user_id != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Access denied - You can only sync your own documents'
            }), 403
        
        # Check that document is not already posted
        if document.status == 'posted':
            return jsonify({
                'success': False,
                'error': 'Cannot sync data for already posted documents'
            }), 400
        
        # Check that SO is assigned
        if not document.so_doc_entry:
            return jsonify({
                'success': False,
                'error': 'No Sales Order assigned to this document'
            }), 400
        
        sap = SAPIntegration()
        
        # Try to fetch latest SO details from SAP B1
        if sap.ensure_logged_in():
            try:
                url = f"{sap.base_url}/b1s/v1/Orders?$filter=DocEntry eq {document.so_doc_entry}"
                response = sap.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    orders = data.get('value', [])
                    
                    if orders:
                        order = orders[0]
                        
                        # Check if SO is still open
                        if order.get("DocumentStatus") != "bost_Open":
                            return jsonify({
                                'success': False,
                                'error': f"Sales Order {document.so_number} is already closed and cannot be synced"
                            }), 400
                        
                        # Update document header information
                        document.card_code = order.get('CardCode', document.card_code)
                        document.card_name = order.get('CardName', document.card_name)
                        document.customer_address = order.get('Address', document.customer_address)
                        
                        # Get open lines only
                        open_lines = [
                            line for line in order.get("DocumentLines", [])
                            if line.get("LineStatus") == "bost_Open"
                        ]
                        
                        # Track changes
                        changes_made = {
                            'lines_added': 0,
                            'lines_updated': 0,
                            'lines_removed': 0
                        }
                        
                        # Get existing line numbers from database
                        existing_items = {item.line_num: item for item in document.items}
                        current_line_nums = set(existing_items.keys())
                        new_line_nums = set(line.get('LineNum') for line in open_lines)
                        
                        # Add or update lines
                        for line in open_lines:
                            line_num = line.get('LineNum')
                            item_code = line.get('ItemCode')
                            description = line.get('ItemDescription', '')
                            quantity = line.get('Quantity', 0)
                            warehouse_code = line.get('WarehouseCode', '')
                            
                            if line_num in existing_items:
                                # Update existing item
                                existing_item = existing_items[line_num]
                                original_qty = existing_item.so_quantity
                                
                                existing_item.item_code = item_code
                                existing_item.item_description = description
                                existing_item.so_quantity = quantity
                                existing_item.warehouse_code = warehouse_code
                                existing_item.updated_at = datetime.utcnow()
                                
                                if original_qty != quantity:
                                    changes_made['lines_updated'] += 1
                                    logging.info(f"Updated line {line_num}: quantity changed from {original_qty} to {quantity}")
                            else:
                                # Add new item
                                new_item = SOInvoiceItem(
                                    so_invoice_id=document.id,
                                    line_num=line_num,
                                    item_code=item_code,
                                    item_description=description,
                                    so_quantity=quantity,
                                    warehouse_code=warehouse_code,
                                    validation_status='pending'
                                )
                                db.session.add(new_item)
                                changes_made['lines_added'] += 1
                                logging.info(f"Added new line {line_num}: {item_code} - {quantity}")
                        
                        # Remove lines that are no longer open
                        removed_lines = current_line_nums - new_line_nums
                        for line_num in removed_lines:
                            item_to_remove = existing_items[line_num]
                            # Only remove if not validated yet
                            if item_to_remove.validation_status == 'pending':
                                db.session.delete(item_to_remove)
                                changes_made['lines_removed'] += 1
                                logging.info(f"Removed line {line_num}: {item_to_remove.item_code}")
                        
                        # Update document timestamp
                        document.updated_at = datetime.utcnow()
                        document.validation_notes = f"Data synced from SAP B1 at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        db.session.commit()
                        
                        # Prepare response summary
                        total_changes = sum(changes_made.values())
                        if total_changes > 0:
                            change_summary = []
                            if changes_made['lines_added']:
                                change_summary.append(f"{changes_made['lines_added']} lines added")
                            if changes_made['lines_updated']:
                                change_summary.append(f"{changes_made['lines_updated']} lines updated")
                            if changes_made['lines_removed']:
                                change_summary.append(f"{changes_made['lines_removed']} lines removed")
                            
                            message = f"Data sync completed: {', '.join(change_summary)}"
                        else:
                            message = "Data sync completed: No changes detected"
                        
                        logging.info(f"SO data sync successful for document {document.document_number}: {message}")
                        
                        return jsonify({
                            'success': True,
                            'message': message,
                            'changes': changes_made,
                            'total_lines': len(open_lines)
                        })
                        
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'Sales Order DocEntry {document.so_doc_entry} not found in SAP B1'
                        }), 404
                        
                else:
                    logging.error(f"Error fetching SO details from SAP: {response.status_code} - {response.text}")
                    return jsonify({
                        'success': False,
                        'error': f'Failed to fetch SO details from SAP B1: HTTP {response.status_code}'
                    }), 502
                    
            except Exception as e:
                logging.error(f"Error syncing SO data from SAP: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to connect to SAP B1 for data sync'
                }), 503
        
        # Strict production check - never allow mock sync in production
        if is_production_environment():
            return jsonify({
                'success': False,
                'error': 'SAP B1 service unavailable - cannot sync data in production without live connection'
            }), 503
        
        # Development mode - return mock sync result
        logging.warning(f"DEVELOPMENT MODE: Mock data sync for document {document.document_number}")
        return jsonify({
            'success': True,
            'message': 'Development mode: Mock data sync completed (no real changes made)',
            'changes': {'lines_added': 0, 'lines_updated': 0, 'lines_removed': 0},
            'total_lines': len(document.items),
            'development_mode': True
        })
    
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in sync_so_data API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500