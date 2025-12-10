"""
Item Tracking Module Routes
Track items by Serial Number using SAP B1 integration
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
import logging
from datetime import datetime
from pathlib import Path

from sap_integration import SAPIntegration

item_tracking_bp = Blueprint('item_tracking', __name__, 
                             template_folder=str(Path(__file__).resolve().parent / 'templates'),
                             url_prefix='/item-tracking')

SAP_DOC_TYPES = {
    2: "Journal Entry",
    4: "Quotation",
    13: "A/R Invoice",
    14: "A/R Credit Memo",
    15: "Delivery",
    16: "Return",
    17: "Sales Order",
    18: "A/P Invoice",
    19: "A/P Credit Memo",
    20: "Goods Receipt PO",
    21: "Goods Return",
    22: "A/R Down Payment Invoice",
    23: "Purchase Order",
    24: "A/R Reserve Invoice",
    46: "A/P Down Payment Invoice",
    59: "Goods Receipt",
    60: "Goods Issue",
    67: "Inventory Transfer",
    68: "Inventory Transfer Draft",
    69: "Inventory Transfer Request",
    140: "Production Receipt from Production",
    141: "Issue for Production",
    156: "Pick List",
    162: "Inventory Counting",
    202: "Production Order",
    234: "Inventory Posting",
    310: "Pick List Draft",
    540000006: "Landed Cost",
    1250000001: "Inventory Opening Balance",
}


def get_doc_type_name(doc_type):
    """Convert SAP DocType number to human-readable document name"""
    return SAP_DOC_TYPES.get(doc_type, f"Unknown ({doc_type})")


def format_sap_date(date_str):
    """Format SAP date string (YYYYMMDD) to readable format"""
    if not date_str:
        return ""
    try:
        if isinstance(date_str, str) and len(date_str) == 8:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            return date_obj.strftime("%d-%b-%Y")
        return str(date_str)
    except:
        return str(date_str)


@item_tracking_bp.route('/')
@login_required
def index():
    """Main Item Tracking page"""
    if not current_user.has_permission('item_tracking'):
        flash('Access denied - Item Tracking permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('item_tracking/index.html')


@item_tracking_bp.route('/search', methods=['POST'])
@login_required
def search():
    """Search for item tracking details by serial number"""
    if not current_user.has_permission('item_tracking'):
        flash('Access denied - Item Tracking permissions required', 'error')
        return redirect(url_for('dashboard'))
    
    serial_number = request.form.get('serial_number', '').strip()
    
    if not serial_number:
        flash('Please enter a serial number', 'warning')
        return redirect(url_for('item_tracking.index'))
    
    try:
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            flash('Unable to connect to SAP B1. Please check SAP connection settings.', 'error')
            return render_template('item_tracking/index.html', 
                                 serial_number=serial_number,
                                 error='SAP connection failed')
        
        tracking_data = fetch_item_tracking(sap, serial_number)
        
        if tracking_data.get('error'):
            flash(tracking_data['error'], 'error')
            return render_template('item_tracking/index.html', 
                                 serial_number=serial_number,
                                 error=tracking_data['error'])
        
        items = tracking_data.get('items', [])
        
        for item in items:
            item['DocTypeName'] = get_doc_type_name(item.get('DocType'))
            item['FormattedDate'] = format_sap_date(item.get('DocDate'))
        
        return render_template('item_tracking/index.html',
                             serial_number=serial_number,
                             items=items,
                             total_records=len(items))
                             
    except Exception as e:
        logging.error(f"Error in item tracking search: {e}")
        flash(f'Error searching for serial number: {str(e)}', 'error')
        return render_template('item_tracking/index.html', 
                             serial_number=serial_number,
                             error=str(e))


@item_tracking_bp.route('/api/search', methods=['POST'])
@login_required
def api_search():
    """API endpoint for item tracking search (for QR code scanner)"""
    if not current_user.has_permission('item_tracking'):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    data = request.get_json() or {}
    serial_number = data.get('serial_number', '').strip()
    
    if not serial_number:
        return jsonify({'success': False, 'error': 'Serial number is required'}), 400
    
    try:
        sap = SAPIntegration()
        if not sap.ensure_logged_in():
            return jsonify({'success': False, 'error': 'SAP connection failed'}), 500
        
        tracking_data = fetch_item_tracking(sap, serial_number)
        
        if tracking_data.get('error'):
            return jsonify({'success': False, 'error': tracking_data['error']}), 400
        
        items = tracking_data.get('items', [])
        
        for item in items:
            item['DocTypeName'] = get_doc_type_name(item.get('DocType'))
            item['FormattedDate'] = format_sap_date(item.get('DocDate'))
        
        return jsonify({
            'success': True,
            'serial_number': serial_number,
            'items': items,
            'total_records': len(items)
        })
        
    except Exception as e:
        logging.error(f"API Error in item tracking search: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def fetch_item_tracking(sap, serial_number):
    """
    Fetch item tracking data from SAP B1 using SQL Query
    
    Args:
        sap: SAPIntegration instance (already logged in)
        serial_number: Serial number to search for
        
    Returns:
        dict with 'items' list or 'error' message
    """
    try:
        url = f"{sap.base_url}/b1s/v1/SQLQueries('item_tracking')/List"
        payload = {
            "ParamList": f"serialNumber='{serial_number}'"
        }
        
        logging.info(f"Fetching item tracking for serial: {serial_number}")
        response = sap.session.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get('value', [])
            logging.info(f"Found {len(items)} tracking records for serial: {serial_number}")
            return {'items': items}
        elif response.status_code == 404:
            return {'error': f"SAP Query 'item_tracking' not found. Please create the query in SAP B1."}
        else:
            error_msg = f"SAP returned status {response.status_code}: {response.text}"
            logging.error(error_msg)
            return {'error': error_msg}
            
    except Exception as e:
        logging.error(f"Error fetching item tracking: {e}")
        return {'error': str(e)}
