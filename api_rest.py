"""
REST API Module for Warehouse Management System
Provides JSON REST API endpoints for all models
Operations: GET (list/detail), POST (create), PATCH (update), DELETE

SECURITY IMPLEMENTATION:
=====================
This module implements role-based access control (RBAC) and resource ownership checks.

Authorization Levels:
1. Admin Only - Full access to all resources (user management, system configuration)
2. Permission-Based - Users must have specific permissions (e.g., 'inventory_transfer', 'grpo')
3. Ownership-Based - Users can only access/modify resources they created
4. Self-Access - Users can view/edit their own user profile only

Security Decorators:
- @require_admin - Requires admin role
- @require_permission('permission_name') - Requires specific permission
- check_resource_ownership(resource) - Validates user owns the resource

Security Pattern Applied To:
✅ User Management (GET, POST, PATCH, DELETE) - Admin only, self-access for viewing
✅ Inventory Transfers (GET, POST, PATCH, DELETE) - Permission + ownership checks
✅ Inventory Transfer Request Lines (GET, POST, PATCH, DELETE) - Permission + ownership checks
✅ Pick Lists (GET, POST, PATCH, DELETE) - Permission + ownership checks
✅ Inventory Counts (GET, POST, PATCH, DELETE) - Permission + ownership checks
✅ GRPO Documents (GET, POST, PATCH, DELETE) - Permission + ownership checks
✅ GRPO Items (GET, POST, PATCH, DELETE) - Permission required
✅ Multi GRN Batches (GET, POST, PATCH, DELETE) - Permission required
✅ Delivery Documents (GET, POST, PATCH, DELETE) - Permission required
✅ Serial Transfers (GET, POST, PATCH, DELETE) - Permission required
✅ Direct Transfers (GET, POST, PATCH, DELETE) - Permission required
✅ QR Labels (GET, POST, PATCH, DELETE) - Login required
✅ SAP Inventory Counts (GET, PATCH) - Permission required
✅ Bin Locations (POST, PATCH, DELETE) - Admin only

ALL ENDPOINTS NOW SECURED WITH PROPER AUTHORIZATION!

Implementation Steps for Each Resource:
1. Add @require_permission decorator to all endpoints
2. Add ownership checks to GET/PATCH/DELETE operations
3. Filter GET list endpoints by user_id for non-admins
4. Prevent users from modifying resources they don't own

Example Pattern:
    @app.route('/api/rest/resource', methods=['GET'])
    @login_required
    @require_permission('permission_name')
    def api_get_resources():
        if check_admin_permission():
            items = Resource.query.all()
        else:
            items = Resource.query.filter_by(user_id=current_user.id).all()
        return jsonify({'success': True, 'data': [serialize_model(i) for i in items]})
"""
from flask import jsonify, request, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app import app, db, login_manager
from models import (
    User, InventoryTransfer, InventoryTransferItem, InventoryTransferRequestLine, TransferScanState,
    PickList, PickListItem, PickListLine, PickListBinAllocation,
    InventoryCount, InventoryCountItem, SAPInventoryCount, SAPInventoryCountLine,
    BarcodeLabel, BinLocation, BinItem, BinScanningLog, QRCodeLabel,
    SalesOrder, SalesOrderLine, DocumentNumberSeries,
    SerialNumberTransfer, SerialNumberTransferItem, SerialNumberTransferSerial,
    SerialItemTransfer, SerialItemTransferItem,
    DirectInventoryTransfer, DirectInventoryTransferItem
)
from modules.grpo.models import GRPODocument, GRPOItem, GRPOSerialNumber, GRPOBatchNumber, PurchaseDeliveryNote, GRPONonManagedItem
from modules.multi_grn_creation.models import MultiGRNBatch, MultiGRNPOLink, MultiGRNLineSelection, MultiGRNBatchDetails, MultiGRNSerialDetails
from modules.sales_delivery.models import DeliveryDocument, DeliveryItem
import json


# ================================
# REST API Unauthorized Handler
# ================================

@login_manager.unauthorized_handler
def unauthorized_api():
    """Handle unauthorized access for REST API endpoints"""
    if request.path.startswith('/api/rest/'):
        return jsonify({
            'success': False,
            'error': 'Authentication required. Please login first.'
        }), 401
    return redirect(url_for('login', next=request.url))


def serialize_model(obj, exclude_fields=None):
    """Serialize SQLAlchemy model to dictionary"""
    if exclude_fields is None:
        exclude_fields = []
    
    result = {}
    for column in obj.__table__.columns:
        if column.name in exclude_fields:
            continue
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            result[column.name] = value.isoformat()
        else:
            result[column.name] = value
    return result


def get_request_data():
    """Get JSON data from request"""
    return request.get_json() or {}


def check_admin_permission():
    """Check if current user is admin"""
    if not current_user.is_authenticated:
        return False
    return current_user.role == 'admin'


def check_permission(permission_name):
    """Check if current user has specific permission"""
    if not current_user.is_authenticated:
        return False
    if current_user.role == 'admin':
        return True
    return current_user.has_permission(permission_name)


def check_user_access(user_id):
    """Check if current user can access another user's data"""
    if not current_user.is_authenticated:
        return False
    if current_user.role == 'admin':
        return True
    return current_user.id == user_id


def check_resource_ownership(resource):
    """Check if current user owns or can access a resource"""
    if not current_user.is_authenticated:
        return False
    if current_user.role == 'admin':
        return True
    if hasattr(resource, 'user_id'):
        return resource.user_id == current_user.id
    return False


def require_admin(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_admin_permission():
            return jsonify({
                'success': False,
                'error': 'Admin permission required'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def require_permission(permission_name):
    """Decorator to require specific permission"""
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permission(permission_name):
                return jsonify({
                    'success': False,
                    'error': f'Permission required: {permission_name}'
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ================================
# Authentication API Endpoints
# ================================

@app.route('/api/rest/auth/login', methods=['POST'])
def api_login():
    """POST login - Authenticate user and create session"""
    try:
        data = get_request_data()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Username and password are required'
            }), 400
        
        from werkzeug.security import check_password_hash
        from flask_login import login_user
        
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({
                'success': False,
                'error': 'Invalid username or password'
            }), 401
        
        if not user.is_active:
            return jsonify({
                'success': False,
                'error': 'User account is inactive'
            }), 403
        
        login_user(user, remember=True)
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'user': serialize_model(user, exclude_fields=['password_hash']),
                'permissions': user.get_permissions()
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/auth/logout', methods=['POST'])
@login_required
def api_logout():
    """POST logout - Invalidate user session"""
    try:
        from flask_login import logout_user
        logout_user()
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/auth/me', methods=['GET'])
@login_required
def api_get_current_user():
    """GET current authenticated user info"""
    try:
        return jsonify({
            'success': True,
            'data': {
                'user': serialize_model(current_user, exclude_fields=['password_hash']),
                'permissions': current_user.get_permissions()
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# User API Endpoints
# ================================

@app.route('/api/rest/users', methods=['GET'])
@login_required
@require_admin
def api_get_users():
    """GET list of all users - Admin only"""
    try:
        users = User.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(u, exclude_fields=['password_hash']) for u in users],
            'count': len(users)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/users/<int:user_id>', methods=['GET'])
@login_required
def api_get_user(user_id):
    """GET single user by ID - Admin or self only"""
    try:
        if not check_user_access(user_id):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own user data'
            }), 403
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        return jsonify({
            'success': True,
            'data': serialize_model(user, exclude_fields=['password_hash'])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/users', methods=['POST'])
@login_required
@require_admin
def api_create_user():
    """POST create new user"""
    try:
        data = get_request_data()
        from werkzeug.security import generate_password_hash
        
        user = User(
            username=data.get('username'),
            email=data.get('email'),
            password_hash=generate_password_hash(data.get('password', 'changeme123')),
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            role=data.get('role', 'user'),
            branch_id=data.get('branch_id'),
            branch_name=data.get('branch_name'),
            is_active=data.get('is_active', True)
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(user, exclude_fields=['password_hash']),
            'message': 'User created successfully'
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'User already exists or validation error'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/users/<int:user_id>', methods=['PATCH'])
@login_required
def api_update_user(user_id):
    """PATCH update user - Admin or self (limited fields)"""
    try:
        if not check_user_access(user_id):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own user data'
            }), 403
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        data = get_request_data()
        
        is_admin = check_admin_permission()
        allowed_fields = ['first_name', 'last_name', 'email']
        admin_only_fields = ['role', 'branch_id', 'branch_name', 'is_active', 'permissions']
        
        for key, value in data.items():
            if key in ['id', 'password_hash', 'username']:
                continue
            if key in admin_only_fields and not is_admin:
                continue
            if key in allowed_fields or (is_admin and key in admin_only_fields):
                if hasattr(user, key):
                    setattr(user, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(user, exclude_fields=['password_hash']),
            'message': 'User updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/users/<int:user_id>', methods=['DELETE'])
@login_required
@require_admin
def api_delete_user(user_id):
    """DELETE user - Admin only"""
    try:
        if user_id == current_user.id:
            return jsonify({
                'success': False,
                'error': 'Cannot delete your own user account'
            }), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        db.session.delete(user)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Inventory Transfer API Endpoints
# ================================

@app.route('/api/rest/inventory-transfers', methods=['GET'])
@login_required
@require_permission('inventory_transfer')
def api_get_inventory_transfers():
    """GET list of inventory transfers - Filtered by ownership"""
    try:
        if check_admin_permission():
            transfers = InventoryTransfer.query.all()
        else:
            transfers = InventoryTransfer.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(t) for t in transfers],
            'count': len(transfers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>', methods=['GET'])
@login_required
@require_permission('inventory_transfer')
def api_get_inventory_transfer(transfer_id):
    """GET single inventory transfer with items - Owner or admin only"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own transfers'
            }), 403
        
        data = serialize_model(transfer)
        data['items'] = [serialize_model(item) for item in transfer.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers', methods=['POST'])
@login_required
@require_permission('inventory_transfer')
def api_create_inventory_transfer():
    """POST create new inventory transfer"""
    try:
        data = get_request_data()
        
        transfer = InventoryTransfer(
            transfer_request_number=data.get('transfer_request_number'),
            user_id=current_user.id,
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            status=data.get('status', 'draft')
        )
        db.session.add(transfer)
        db.session.flush()
        
        for item_data in data.get('items', []):
            item = InventoryTransferItem(
                inventory_transfer_id=transfer.id,
                item_code=item_data.get('item_code'),
                item_name=item_data.get('item_name'),
                quantity=item_data.get('quantity'),
                requested_quantity=item_data.get('requested_quantity'),
                remaining_quantity=item_data.get('remaining_quantity'),
                unit_of_measure=item_data.get('unit_of_measure'),
                from_bin=item_data.get('from_bin'),
                to_bin=item_data.get('to_bin'),
                batch_number=item_data.get('batch_number')
            )
            db.session.add(item)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Inventory transfer created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>', methods=['PATCH'])
@login_required
@require_permission('inventory_transfer')
def api_update_inventory_transfer(transfer_id):
    """PATCH update inventory transfer - Owner or admin only"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own transfers'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if key != 'items' and hasattr(transfer, key):
                setattr(transfer, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Inventory transfer updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>', methods=['DELETE'])
@login_required
@require_permission('inventory_transfer')
def api_delete_inventory_transfer(transfer_id):
    """DELETE inventory transfer - Owner or admin only"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own transfers'
            }), 403
        
        db.session.delete(transfer)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Inventory transfer deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Inventory Transfer Request Lines API Endpoints
# ================================

@app.route('/api/rest/inventory-transfer-request-lines', methods=['GET'])
@login_required
@require_permission('inventory_transfer')
def api_get_transfer_request_lines():
    """
    GET list of inventory transfer request lines
    Query params:
    - transfer_id: Filter by inventory transfer ID (required for non-admins)
    - item_code: Filter by item code (optional)
    - line_status: Filter by line status (optional)
    """
    try:
        transfer_id = request.args.get('transfer_id', type=int)
        item_code = request.args.get('item_code')
        line_status = request.args.get('line_status')
        
        query = InventoryTransferRequestLine.query
        
        if transfer_id:
            transfer = InventoryTransfer.query.get(transfer_id)
            if not transfer:
                return jsonify({'success': False, 'error': 'Transfer not found'}), 404
            if not check_resource_ownership(transfer):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view lines for your own transfers'
                }), 403
            query = query.filter_by(inventory_transfer_id=transfer_id)
        elif not check_admin_permission():
            user_transfers = InventoryTransfer.query.filter_by(user_id=current_user.id).all()
            transfer_ids = [t.id for t in user_transfers]
            query = query.filter(InventoryTransferRequestLine.inventory_transfer_id.in_(transfer_ids))
        
        if item_code:
            query = query.filter_by(item_code=item_code)
        if line_status:
            query = query.filter_by(line_status=line_status)
        
        lines = query.all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(line) for line in lines],
            'count': len(lines)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfer-request-lines/<int:line_id>', methods=['GET'])
@login_required
@require_permission('inventory_transfer')
def api_get_transfer_request_line(line_id):
    """GET single inventory transfer request line by ID"""
    try:
        line = InventoryTransferRequestLine.query.get(line_id)
        if not line:
            return jsonify({'success': False, 'error': 'Transfer request line not found'}), 404
        
        transfer = InventoryTransfer.query.get(line.inventory_transfer_id)
        if transfer and not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view lines for your own transfers'
            }), 403
        
        data = serialize_model(line)
        if transfer:
            data['transfer_request_number'] = transfer.transfer_request_number
            data['from_warehouse'] = transfer.from_warehouse
            data['to_warehouse'] = transfer.to_warehouse
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>/request-lines', methods=['GET'])
@login_required
@require_permission('inventory_transfer')
def api_get_transfer_request_lines_by_transfer(transfer_id):
    """GET all request lines for a specific inventory transfer"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view lines for your own transfers'
            }), 403
        
        lines = InventoryTransferRequestLine.query.filter_by(
            inventory_transfer_id=transfer_id
        ).order_by(InventoryTransferRequestLine.line_num).all()
        
        transfer_data = serialize_model(transfer)
        lines_data = [serialize_model(line) for line in lines]
        
        return jsonify({
            'success': True,
            'data': {
                'transfer': transfer_data,
                'request_lines': lines_data,
                'count': len(lines_data)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfer-request-lines', methods=['POST'])
@login_required
@require_permission('inventory_transfer')
def api_create_transfer_request_line():
    """POST create new inventory transfer request line"""
    try:
        data = get_request_data()
        
        transfer_id = data.get('inventory_transfer_id')
        if not transfer_id:
            return jsonify({'success': False, 'error': 'inventory_transfer_id is required'}), 400
        
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add lines to your own transfers'
            }), 403
        
        if not data.get('item_code'):
            return jsonify({'success': False, 'error': 'item_code is required'}), 400
        if data.get('quantity') is None:
            return jsonify({'success': False, 'error': 'quantity is required'}), 400
        
        line = InventoryTransferRequestLine(
            inventory_transfer_id=transfer_id,
            line_num=data.get('line_num', 0),
            sap_doc_entry=data.get('sap_doc_entry', 0),
            item_code=data.get('item_code'),
            item_description=data.get('item_description'),
            quantity=data.get('quantity'),
            warehouse_code=data.get('warehouse_code'),
            from_warehouse_code=data.get('from_warehouse_code'),
            remaining_open_quantity=data.get('remaining_open_quantity'),
            line_status=data.get('line_status', 'bost_Open'),
            uom_code=data.get('uom_code'),
            transferred_quantity=data.get('transferred_quantity', 0),
            wms_remaining_quantity=data.get('wms_remaining_quantity')
        )
        db.session.add(line)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(line),
            'message': 'Transfer request line created successfully'
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Validation error or constraint violation'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfer-request-lines/<int:line_id>', methods=['PATCH'])
@login_required
@require_permission('inventory_transfer')
def api_update_transfer_request_line(line_id):
    """PATCH update inventory transfer request line"""
    try:
        line = InventoryTransferRequestLine.query.get(line_id)
        if not line:
            return jsonify({'success': False, 'error': 'Transfer request line not found'}), 404
        
        transfer = InventoryTransfer.query.get(line.inventory_transfer_id)
        if transfer and not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update lines for your own transfers'
            }), 403
        
        data = get_request_data()
        
        readonly_fields = ['id', 'inventory_transfer_id', 'created_at']
        
        for key, value in data.items():
            if key in readonly_fields:
                continue
            if hasattr(line, key):
                setattr(line, key, value)
        
        line.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(line),
            'message': 'Transfer request line updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfer-request-lines/<int:line_id>', methods=['DELETE'])
@login_required
@require_permission('inventory_transfer')
def api_delete_transfer_request_line(line_id):
    """DELETE inventory transfer request line"""
    try:
        line = InventoryTransferRequestLine.query.get(line_id)
        if not line:
            return jsonify({'success': False, 'error': 'Transfer request line not found'}), 404
        
        transfer = InventoryTransfer.query.get(line.inventory_transfer_id)
        if transfer and not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete lines for your own transfers'
            }), 403
        
        db.session.delete(line)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Transfer request line deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>/request-lines', methods=['POST'])
@login_required
@require_permission('inventory_transfer')
def api_create_transfer_request_lines_bulk(transfer_id):
    """POST create multiple inventory transfer request lines for a transfer"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add lines to your own transfers'
            }), 403
        
        data = get_request_data()
        lines_data = data.get('lines', [])
        
        if not lines_data:
            return jsonify({'success': False, 'error': 'No lines provided'}), 400
        
        created_lines = []
        for line_data in lines_data:
            if not line_data.get('item_code'):
                continue
            
            line = InventoryTransferRequestLine(
                inventory_transfer_id=transfer_id,
                line_num=line_data.get('line_num', 0),
                sap_doc_entry=line_data.get('sap_doc_entry', 0),
                item_code=line_data.get('item_code'),
                item_description=line_data.get('item_description'),
                quantity=line_data.get('quantity', 0),
                warehouse_code=line_data.get('warehouse_code'),
                from_warehouse_code=line_data.get('from_warehouse_code'),
                remaining_open_quantity=line_data.get('remaining_open_quantity'),
                line_status=line_data.get('line_status', 'bost_Open'),
                uom_code=line_data.get('uom_code'),
                transferred_quantity=line_data.get('transferred_quantity', 0),
                wms_remaining_quantity=line_data.get('wms_remaining_quantity')
            )
            db.session.add(line)
            created_lines.append(line)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(line) for line in created_lines],
            'count': len(created_lines),
            'message': f'{len(created_lines)} transfer request lines created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-transfers/<int:transfer_id>/request-lines', methods=['DELETE'])
@login_required
@require_permission('inventory_transfer')
def api_delete_transfer_request_lines_bulk(transfer_id):
    """DELETE all inventory transfer request lines for a transfer"""
    try:
        transfer = InventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete lines for your own transfers'
            }), 403
        
        deleted_count = InventoryTransferRequestLine.query.filter_by(
            inventory_transfer_id=transfer_id
        ).delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{deleted_count} transfer request lines deleted successfully',
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Pick List API Endpoints
# ================================

@app.route('/api/rest/pick-lists', methods=['GET'])
@login_required
@require_permission('pick_list')
def api_get_pick_lists():
    """GET list of pick lists - Filtered by ownership"""
    try:
        if check_admin_permission():
            pick_lists = PickList.query.all()
        else:
            pick_lists = PickList.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(pl) for pl in pick_lists],
            'count': len(pick_lists)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/pick-lists/<int:pick_list_id>', methods=['GET'])
@login_required
@require_permission('pick_list')
def api_get_pick_list(pick_list_id):
    """GET single pick list with items - Owner or admin only"""
    try:
        pick_list = PickList.query.get(pick_list_id)
        if not pick_list:
            return jsonify({'success': False, 'error': 'Pick list not found'}), 404
        
        if not check_resource_ownership(pick_list):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own pick lists'
            }), 403
        
        data = serialize_model(pick_list)
        data['items'] = [serialize_model(item) for item in pick_list.items]
        data['lines'] = [serialize_model(line) for line in pick_list.lines]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/pick-lists', methods=['POST'])
@login_required
@require_permission('pick_list')
def api_create_pick_list():
    """POST create new pick list"""
    try:
        data = get_request_data()
        
        pick_list = PickList(
            name=data.get('name'),
            user_id=current_user.id,
            status=data.get('status', 'pending'),
            warehouse_code=data.get('warehouse_code'),
            customer_code=data.get('customer_code'),
            customer_name=data.get('customer_name'),
            notes=data.get('notes')
        )
        db.session.add(pick_list)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(pick_list),
            'message': 'Pick list created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/pick-lists/<int:pick_list_id>', methods=['PATCH'])
@login_required
@require_permission('pick_list')
def api_update_pick_list(pick_list_id):
    """PATCH update pick list - Owner or admin only"""
    try:
        pick_list = PickList.query.get(pick_list_id)
        if not pick_list:
            return jsonify({'success': False, 'error': 'Pick list not found'}), 404
        
        if not check_resource_ownership(pick_list):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own pick lists'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(pick_list, key):
                setattr(pick_list, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(pick_list),
            'message': 'Pick list updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/pick-lists/<int:pick_list_id>', methods=['DELETE'])
@login_required
@require_permission('pick_list')
def api_delete_pick_list(pick_list_id):
    """DELETE pick list - Owner or admin only"""
    try:
        pick_list = PickList.query.get(pick_list_id)
        if not pick_list:
            return jsonify({'success': False, 'error': 'Pick list not found'}), 404
        
        if not check_resource_ownership(pick_list):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own pick lists'
            }), 403
        
        db.session.delete(pick_list)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Pick list deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Inventory Count API Endpoints
# ================================

@app.route('/api/rest/inventory-counts', methods=['GET'])
@login_required
@require_permission('inventory_counting')
def api_get_inventory_counts():
    """GET list of inventory counts - Filtered by ownership"""
    try:
        if check_admin_permission():
            counts = InventoryCount.query.all()
        else:
            counts = InventoryCount.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(c) for c in counts],
            'count': len(counts)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-counts/<int:count_id>', methods=['GET'])
@login_required
@require_permission('inventory_counting')
def api_get_inventory_count(count_id):
    """GET single inventory count with items - Owner or admin only"""
    try:
        count = InventoryCount.query.get(count_id)
        if not count:
            return jsonify({'success': False, 'error': 'Inventory count not found'}), 404
        
        if not check_resource_ownership(count):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own inventory counts'
            }), 403
        
        data = serialize_model(count)
        data['items'] = [serialize_model(item) for item in count.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-counts', methods=['POST'])
@login_required
@require_permission('inventory_counting')
def api_create_inventory_count():
    """POST create new inventory count"""
    try:
        data = get_request_data()
        
        count = InventoryCount(
            count_number=data.get('count_number'),
            warehouse_code=data.get('warehouse_code'),
            bin_location=data.get('bin_location'),
            user_id=current_user.id,
            status=data.get('status', 'assigned')
        )
        db.session.add(count)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(count),
            'message': 'Inventory count created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-counts/<int:count_id>', methods=['PATCH'])
@login_required
@require_permission('inventory_counting')
def api_update_inventory_count(count_id):
    """PATCH update inventory count - Owner or admin only"""
    try:
        count = InventoryCount.query.get(count_id)
        if not count:
            return jsonify({'success': False, 'error': 'Inventory count not found'}), 404
        
        if not check_resource_ownership(count):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own inventory counts'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(count, key):
                setattr(count, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(count),
            'message': 'Inventory count updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/inventory-counts/<int:count_id>', methods=['DELETE'])
@login_required
@require_permission('inventory_counting')
def api_delete_inventory_count(count_id):
    """DELETE inventory count - Owner or admin only"""
    try:
        count = InventoryCount.query.get(count_id)
        if not count:
            return jsonify({'success': False, 'error': 'Inventory count not found'}), 404
        
        if not check_resource_ownership(count):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own inventory counts'
            }), 403
        
        db.session.delete(count)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Inventory count deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Bin Location API Endpoints
# ================================

@app.route('/api/rest/bin-locations', methods=['GET'])
@login_required
def api_get_bin_locations():
    """GET list of bin locations"""
    try:
        bins = BinLocation.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(b) for b in bins],
            'count': len(bins)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/bin-locations/<int:bin_id>', methods=['GET'])
@login_required
def api_get_bin_location(bin_id):
    """GET single bin location with items"""
    try:
        bin_loc = BinLocation.query.get(bin_id)
        if not bin_loc:
            return jsonify({'success': False, 'error': 'Bin location not found'}), 404
        
        data = serialize_model(bin_loc)
        data['items'] = [serialize_model(item) for item in bin_loc.bin_items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/bin-locations', methods=['POST'])
@login_required
@require_admin
def api_create_bin_location():
    """POST create new bin location"""
    try:
        data = get_request_data()
        
        bin_loc = BinLocation(
            bin_code=data.get('bin_code'),
            warehouse_code=data.get('warehouse_code'),
            description=data.get('description'),
            bin_name=data.get('bin_name'),
            is_active=data.get('is_active', True)
        )
        db.session.add(bin_loc)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(bin_loc),
            'message': 'Bin location created successfully'
        }), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Bin code already exists'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/bin-locations/<int:bin_id>', methods=['PATCH'])
@login_required
@require_admin
def api_update_bin_location(bin_id):
    """PATCH update bin location"""
    try:
        bin_loc = BinLocation.query.get(bin_id)
        if not bin_loc:
            return jsonify({'success': False, 'error': 'Bin location not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(bin_loc, key):
                setattr(bin_loc, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(bin_loc),
            'message': 'Bin location updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/bin-locations/<int:bin_id>', methods=['DELETE'])
@login_required
@require_admin
def api_delete_bin_location(bin_id):
    """DELETE bin location"""
    try:
        bin_loc = BinLocation.query.get(bin_id)
        if not bin_loc:
            return jsonify({'success': False, 'error': 'Bin location not found'}), 404
        
        db.session.delete(bin_loc)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Bin location deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# GRPO Document API Endpoints
# ================================

@app.route('/api/rest/grpo-documents', methods=['GET'])
@login_required
@require_permission('grpo')
def api_get_grpo_documents():
    """GET list of GRPO documents - Filtered by ownership"""
    try:
        if check_admin_permission():
            documents = GRPODocument.query.all()
        else:
            documents = GRPODocument.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(d) for d in documents],
            'count': len(documents)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-documents/<int:doc_id>', methods=['GET'])
@login_required
@require_permission('grpo')
def api_get_grpo_document(doc_id):
    """GET single GRPO document with items - Owner or admin only"""
    try:
        doc = GRPODocument.query.get(doc_id)
        if not doc:
            return jsonify({'success': False, 'error': 'GRPO document not found'}), 404
        
        if not check_resource_ownership(doc):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own GRPO documents'
            }), 403
        
        data = serialize_model(doc)
        data['items'] = [serialize_model(item) for item in doc.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-documents', methods=['POST'])
@login_required
@require_permission('grpo')
def api_create_grpo_document():
    """POST create new GRPO document"""
    try:
        data = get_request_data()
        
        doc = GRPODocument(
            po_number=data.get('po_number'),
            doc_number=data.get('doc_number'),
            supplier_code=data.get('supplier_code'),
            supplier_name=data.get('supplier_name'),
            warehouse_code=data.get('warehouse_code'),
            user_id=current_user.id,
            status=data.get('status', 'draft'),
            notes=data.get('notes')
        )
        db.session.add(doc)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(doc),
            'message': 'GRPO document created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-documents/<int:doc_id>', methods=['PATCH'])
@login_required
@require_permission('grpo')
def api_update_grpo_document(doc_id):
    """PATCH update GRPO document - Owner or admin only"""
    try:
        doc = GRPODocument.query.get(doc_id)
        if not doc:
            return jsonify({'success': False, 'error': 'GRPO document not found'}), 404
        
        if not check_resource_ownership(doc):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own GRPO documents'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(doc, key):
                setattr(doc, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(doc),
            'message': 'GRPO document updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-documents/<int:doc_id>', methods=['DELETE'])
@login_required
@require_permission('grpo')
def api_delete_grpo_document(doc_id):
    """DELETE GRPO document - Owner or admin only"""
    try:
        doc = GRPODocument.query.get(doc_id)
        if not doc:
            return jsonify({'success': False, 'error': 'GRPO document not found'}), 404
        
        if not check_resource_ownership(doc):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own GRPO documents'
            }), 403
        
        db.session.delete(doc)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'GRPO document deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# GRPO Item API Endpoints
# ================================

@app.route('/api/rest/grpo-items', methods=['GET'])
@login_required
@require_permission('grpo')
def api_get_grpo_items():
    """GET list of GRPO items"""
    try:
        grpo_id = request.args.get('grpo_id')
        if grpo_id:
            items = GRPOItem.query.filter_by(grpo_id=grpo_id).all()
        else:
            items = GRPOItem.query.all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(i) for i in items],
            'count': len(items)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-items/<int:item_id>', methods=['GET'])
@login_required
@require_permission('grpo')
def api_get_grpo_item(item_id):
    """GET single GRPO item"""
    try:
        item = GRPOItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'GRPO item not found'}), 404
        
        return jsonify({'success': True, 'data': serialize_model(item)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-items', methods=['POST'])
@login_required
@require_permission('grpo')
def api_create_grpo_item():
    """POST create new GRPO item"""
    try:
        data = get_request_data()
        
        item = GRPOItem(
            grpo_id=data.get('grpo_id'),
            item_code=data.get('item_code'),
            item_name=data.get('item_name'),
            quantity=data.get('quantity'),
            unit_of_measure=data.get('unit_of_measure'),
            warehouse_code=data.get('warehouse_code'),
            bin_location=data.get('bin_location')
        )
        db.session.add(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(item),
            'message': 'GRPO item created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-items/<int:item_id>', methods=['PATCH'])
@login_required
@require_permission('grpo')
def api_update_grpo_item(item_id):
    """PATCH update GRPO item"""
    try:
        item = GRPOItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'GRPO item not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(item),
            'message': 'GRPO item updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/grpo-items/<int:item_id>', methods=['DELETE'])
@login_required
@require_permission('grpo')
def api_delete_grpo_item(item_id):
    """DELETE GRPO item"""
    try:
        item = GRPOItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'GRPO item not found'}), 404
        
        db.session.delete(item)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'GRPO item deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Multi GRN Batch API Endpoints
# ================================

@app.route('/api/rest/multi-grn-batches', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_batches():
    """GET list of multi GRN batches - Filtered by ownership"""
    try:
        if check_admin_permission():
            batches = MultiGRNBatch.query.all()
        else:
            batches = MultiGRNBatch.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(b) for b in batches],
            'count': len(batches)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batches/<int:batch_id>', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_batch(batch_id):
    """GET single multi GRN batch with PO links - Owner or admin only"""
    try:
        batch = MultiGRNBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'Multi GRN batch not found'}), 404
        
        if not check_resource_ownership(batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own Multi GRN batches'
            }), 403
        
        data = serialize_model(batch)
        data['po_links'] = [serialize_model(link) for link in batch.po_links]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batches', methods=['POST'])
@require_permission('multiple_grn')
@login_required
def api_create_multi_grn_batch():
    """POST create new multi GRN batch"""
    try:
        data = get_request_data()
        
        batch = MultiGRNBatch(
            batch_number=data.get('batch_number'),
            user_id=current_user.id,
            customer_code=data.get('customer_code'),
            customer_name=data.get('customer_name'),
            status=data.get('status', 'draft')
        )
        db.session.add(batch)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(batch),
            'message': 'Multi GRN batch created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batches/<int:batch_id>', methods=['PATCH'])
@require_permission('multiple_grn')
@login_required
def api_update_multi_grn_batch(batch_id):
    """PATCH update multi GRN batch - Owner or admin only"""
    try:
        batch = MultiGRNBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'Multi GRN batch not found'}), 404
        
        if not check_resource_ownership(batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own Multi GRN batches'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(batch, key):
                setattr(batch, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(batch),
            'message': 'Multi GRN batch updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batches/<int:batch_id>', methods=['DELETE'])
@require_permission('multiple_grn')
@login_required
def api_delete_multi_grn_batch(batch_id):
    """DELETE multi GRN batch - Owner or admin only"""
    try:
        batch = MultiGRNBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'Multi GRN batch not found'}), 404
        
        if not check_resource_ownership(batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own Multi GRN batches'
            }), 403
        
        db.session.delete(batch)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Multi GRN batch deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Multi GRN PO Links API Endpoints
# ================================

@app.route('/api/rest/multi-grn-po-links', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_po_links():
    """GET list of multi GRN PO links - Filtered by batch ownership"""
    try:
        batch_id = request.args.get('batch_id', type=int)
        
        if batch_id:
            batch = MultiGRNBatch.query.get(batch_id)
            if batch and not check_resource_ownership(batch):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view PO links from your own batches'
                }), 403
            po_links = MultiGRNPOLink.query.filter_by(batch_id=batch_id).all()
        elif check_admin_permission():
            po_links = MultiGRNPOLink.query.all()
        else:
            user_batches = MultiGRNBatch.query.filter_by(user_id=current_user.id).all()
            batch_ids = [b.id for b in user_batches]
            po_links = MultiGRNPOLink.query.filter(MultiGRNPOLink.batch_id.in_(batch_ids)).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(link) for link in po_links],
            'count': len(po_links)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-po-links/<int:link_id>', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_po_link(link_id):
    """GET single multi GRN PO link with line selections - Owner or admin only"""
    try:
        po_link = MultiGRNPOLink.query.get(link_id)
        if not po_link:
            return jsonify({'success': False, 'error': 'PO link not found'}), 404
        
        if not check_resource_ownership(po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view PO links from your own batches'
            }), 403
        
        data = serialize_model(po_link)
        data['line_selections'] = [serialize_model(line) for line in po_link.line_selections]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-po-links', methods=['POST'])
@require_permission('multiple_grn')
@login_required
def api_create_multi_grn_po_link():
    """POST create new multi GRN PO link"""
    try:
        data = get_request_data()
        
        batch_id = data.get('batch_id')
        if not batch_id:
            return jsonify({'success': False, 'error': 'batch_id is required'}), 400
        
        batch = MultiGRNBatch.query.get(batch_id)
        if not batch:
            return jsonify({'success': False, 'error': 'Batch not found'}), 404
        
        if not check_resource_ownership(batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add PO links to your own batches'
            }), 403
        
        po_link = MultiGRNPOLink(
            batch_id=batch_id,
            po_doc_entry=data.get('po_doc_entry'),
            po_doc_num=data.get('po_doc_num'),
            po_card_code=data.get('po_card_code'),
            po_card_name=data.get('po_card_name'),
            po_doc_date=data.get('po_doc_date'),
            po_doc_total=data.get('po_doc_total'),
            status=data.get('status', 'selected')
        )
        db.session.add(po_link)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(po_link),
            'message': 'PO link created successfully'
        }), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Duplicate PO link for this batch'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-po-links/<int:link_id>', methods=['PATCH'])
@require_permission('multiple_grn')
@login_required
def api_update_multi_grn_po_link(link_id):
    """PATCH update multi GRN PO link - Owner or admin only"""
    try:
        po_link = MultiGRNPOLink.query.get(link_id)
        if not po_link:
            return jsonify({'success': False, 'error': 'PO link not found'}), 404
        
        if not check_resource_ownership(po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update PO links from your own batches'
            }), 403
        
        data = get_request_data()
        allowed_fields = ['po_doc_entry', 'po_doc_num', 'po_card_code', 'po_card_name', 
                         'po_doc_date', 'po_doc_total', 'status', 'sap_grn_doc_num', 
                         'sap_grn_doc_entry', 'posted_at', 'error_message']
        
        for key, value in data.items():
            if key in allowed_fields:
                setattr(po_link, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(po_link),
            'message': 'PO link updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-po-links/<int:link_id>', methods=['DELETE'])
@require_permission('multiple_grn')
@login_required
def api_delete_multi_grn_po_link(link_id):
    """DELETE multi GRN PO link - Owner or admin only"""
    try:
        po_link = MultiGRNPOLink.query.get(link_id)
        if not po_link:
            return jsonify({'success': False, 'error': 'PO link not found'}), 404
        
        if not check_resource_ownership(po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete PO links from your own batches'
            }), 403
        
        db.session.delete(po_link)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'PO link deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Multi GRN Line Selection API Endpoints
# ================================

@app.route('/api/rest/multi-grn-line-selections', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_line_selections():
    """GET list of multi GRN line selections - Filtered by batch ownership"""
    try:
        po_link_id = request.args.get('po_link_id', type=int)
        batch_id = request.args.get('batch_id', type=int)
        
        if po_link_id:
            po_link = MultiGRNPOLink.query.get(po_link_id)
            if po_link and not check_resource_ownership(po_link.batch):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view line selections from your own batches'
                }), 403
            line_selections = MultiGRNLineSelection.query.filter_by(po_link_id=po_link_id).all()
        elif batch_id:
            batch = MultiGRNBatch.query.get(batch_id)
            if batch and not check_resource_ownership(batch):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view line selections from your own batches'
                }), 403
            po_links = MultiGRNPOLink.query.filter_by(batch_id=batch_id).all()
            po_link_ids = [link.id for link in po_links]
            line_selections = MultiGRNLineSelection.query.filter(MultiGRNLineSelection.po_link_id.in_(po_link_ids)).all()
        elif check_admin_permission():
            line_selections = MultiGRNLineSelection.query.all()
        else:
            user_batches = MultiGRNBatch.query.filter_by(user_id=current_user.id).all()
            batch_ids = [b.id for b in user_batches]
            po_links = MultiGRNPOLink.query.filter(MultiGRNPOLink.batch_id.in_(batch_ids)).all()
            po_link_ids = [link.id for link in po_links]
            line_selections = MultiGRNLineSelection.query.filter(MultiGRNLineSelection.po_link_id.in_(po_link_ids)).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(line) for line in line_selections],
            'count': len(line_selections)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-line-selections/<int:line_id>', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_line_selection(line_id):
    """GET single multi GRN line selection with batch and serial details - Owner or admin only"""
    try:
        line_selection = MultiGRNLineSelection.query.get(line_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line selection not found'}), 404
        
        if not check_resource_ownership(line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view line selections from your own batches'
            }), 403
        
        data = serialize_model(line_selection)
        data['batch_details'] = [serialize_model(batch) for batch in line_selection.batch_details]
        data['serial_details'] = [serialize_model(serial) for serial in line_selection.serial_details]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-line-selections', methods=['POST'])
@require_permission('multiple_grn')
@login_required
def api_create_multi_grn_line_selection():
    """POST create new multi GRN line selection"""
    try:
        data = get_request_data()
        
        po_link_id = data.get('po_link_id')
        if not po_link_id:
            return jsonify({'success': False, 'error': 'po_link_id is required'}), 400
        
        po_link = MultiGRNPOLink.query.get(po_link_id)
        if not po_link:
            return jsonify({'success': False, 'error': 'PO link not found'}), 404
        
        if not check_resource_ownership(po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add line selections to your own batches'
            }), 403
        
        line_selection = MultiGRNLineSelection(
            po_link_id=po_link_id,
            po_line_num=data.get('po_line_num'),
            item_code=data.get('item_code'),
            item_description=data.get('item_description'),
            ordered_quantity=data.get('ordered_quantity'),
            open_quantity=data.get('open_quantity'),
            selected_quantity=data.get('selected_quantity'),
            warehouse_code=data.get('warehouse_code'),
            bin_location=data.get('bin_location'),
            unit_price=data.get('unit_price'),
            unit_of_measure=data.get('unit_of_measure'),
            line_status=data.get('line_status'),
            inventory_type=data.get('inventory_type'),
            batch_required=data.get('batch_required', 'N'),
            serial_required=data.get('serial_required', 'N'),
            manage_method=data.get('manage_method', 'N')
        )
        db.session.add(line_selection)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(line_selection),
            'message': 'Line selection created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-line-selections/<int:line_id>', methods=['PATCH'])
@require_permission('multiple_grn')
@login_required
def api_update_multi_grn_line_selection(line_id):
    """PATCH update multi GRN line selection - Owner or admin only"""
    try:
        line_selection = MultiGRNLineSelection.query.get(line_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line selection not found'}), 404
        
        if not check_resource_ownership(line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update line selections from your own batches'
            }), 403
        
        data = get_request_data()
        allowed_fields = ['po_line_num', 'item_code', 'item_description', 'ordered_quantity',
                         'open_quantity', 'selected_quantity', 'warehouse_code', 'bin_location',
                         'unit_price', 'unit_of_measure', 'line_status', 'inventory_type',
                         'serial_numbers', 'batch_numbers', 'posting_payload', 'barcode_generated',
                         'batch_required', 'serial_required', 'manage_method']
        
        for key, value in data.items():
            if key in allowed_fields:
                setattr(line_selection, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(line_selection),
            'message': 'Line selection updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-line-selections/<int:line_id>', methods=['DELETE'])
@require_permission('multiple_grn')
@login_required
def api_delete_multi_grn_line_selection(line_id):
    """DELETE multi GRN line selection - Owner or admin only"""
    try:
        line_selection = MultiGRNLineSelection.query.get(line_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line selection not found'}), 404
        
        if not check_resource_ownership(line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete line selections from your own batches'
            }), 403
        
        db.session.delete(line_selection)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Line selection deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Multi GRN Batch Details API Endpoints
# ================================

@app.route('/api/rest/multi-grn-batch-details', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_batch_details():
    """GET list of multi GRN batch details - Filtered by batch ownership"""
    try:
        line_selection_id = request.args.get('line_selection_id', type=int)
        
        if line_selection_id:
            line_selection = MultiGRNLineSelection.query.get(line_selection_id)
            if line_selection and not check_resource_ownership(line_selection.po_link.batch):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view batch details from your own batches'
                }), 403
            batch_details = MultiGRNBatchDetails.query.filter_by(line_selection_id=line_selection_id).all()
        elif check_admin_permission():
            batch_details = MultiGRNBatchDetails.query.all()
        else:
            user_batches = MultiGRNBatch.query.filter_by(user_id=current_user.id).all()
            batch_ids = [b.id for b in user_batches]
            po_links = MultiGRNPOLink.query.filter(MultiGRNPOLink.batch_id.in_(batch_ids)).all()
            po_link_ids = [link.id for link in po_links]
            line_selections = MultiGRNLineSelection.query.filter(MultiGRNLineSelection.po_link_id.in_(po_link_ids)).all()
            line_selection_ids = [line.id for line in line_selections]
            batch_details = MultiGRNBatchDetails.query.filter(MultiGRNBatchDetails.line_selection_id.in_(line_selection_ids)).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(detail) for detail in batch_details],
            'count': len(batch_details)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batch-details/<int:detail_id>', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_batch_detail(detail_id):
    """GET single multi GRN batch detail - Owner or admin only"""
    try:
        batch_detail = MultiGRNBatchDetails.query.get(detail_id)
        if not batch_detail:
            return jsonify({'success': False, 'error': 'Batch detail not found'}), 404
        
        if not check_resource_ownership(batch_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view batch details from your own batches'
            }), 403
        
        return jsonify({'success': True, 'data': serialize_model(batch_detail)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batch-details', methods=['POST'])
@require_permission('multiple_grn')
@login_required
def api_create_multi_grn_batch_detail():
    """POST create new multi GRN batch detail"""
    try:
        data = get_request_data()
        
        line_selection_id = data.get('line_selection_id')
        if not line_selection_id:
            return jsonify({'success': False, 'error': 'line_selection_id is required'}), 400
        
        line_selection = MultiGRNLineSelection.query.get(line_selection_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line selection not found'}), 404
        
        if not check_resource_ownership(line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add batch details to your own batches'
            }), 403
        
        batch_detail = MultiGRNBatchDetails(
            line_selection_id=line_selection_id,
            batch_number=data.get('batch_number'),
            quantity=data.get('quantity'),
            manufacturer_serial_number=data.get('manufacturer_serial_number'),
            internal_serial_number=data.get('internal_serial_number'),
            expiry_date=data.get('expiry_date'),
            barcode=data.get('barcode'),
            grn_number=data.get('grn_number'),
            qty_per_pack=data.get('qty_per_pack'),
            no_of_packs=data.get('no_of_packs', 1)
        )
        db.session.add(batch_detail)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(batch_detail),
            'message': 'Batch detail created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batch-details/<int:detail_id>', methods=['PATCH'])
@require_permission('multiple_grn')
@login_required
def api_update_multi_grn_batch_detail(detail_id):
    """PATCH update multi GRN batch detail - Owner or admin only"""
    try:
        batch_detail = MultiGRNBatchDetails.query.get(detail_id)
        if not batch_detail:
            return jsonify({'success': False, 'error': 'Batch detail not found'}), 404
        
        if not check_resource_ownership(batch_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update batch details from your own batches'
            }), 403
        
        data = get_request_data()
        allowed_fields = ['batch_number', 'quantity', 'manufacturer_serial_number',
                         'internal_serial_number', 'expiry_date', 'barcode', 'grn_number',
                         'qty_per_pack', 'no_of_packs']
        
        for key, value in data.items():
            if key in allowed_fields:
                setattr(batch_detail, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(batch_detail),
            'message': 'Batch detail updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-batch-details/<int:detail_id>', methods=['DELETE'])
@require_permission('multiple_grn')
@login_required
def api_delete_multi_grn_batch_detail(detail_id):
    """DELETE multi GRN batch detail - Owner or admin only"""
    try:
        batch_detail = MultiGRNBatchDetails.query.get(detail_id)
        if not batch_detail:
            return jsonify({'success': False, 'error': 'Batch detail not found'}), 404
        
        if not check_resource_ownership(batch_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete batch details from your own batches'
            }), 403
        
        db.session.delete(batch_detail)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Batch detail deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Multi GRN Serial Details API Endpoints
# ================================

@app.route('/api/rest/multi-grn-serial-details', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_serial_details():
    """GET list of multi GRN serial details - Filtered by batch ownership"""
    try:
        line_selection_id = request.args.get('line_selection_id', type=int)
        
        if line_selection_id:
            line_selection = MultiGRNLineSelection.query.get(line_selection_id)
            if line_selection and not check_resource_ownership(line_selection.po_link.batch):
                return jsonify({
                    'success': False,
                    'error': 'Access denied: You can only view serial details from your own batches'
                }), 403
            serial_details = MultiGRNSerialDetails.query.filter_by(line_selection_id=line_selection_id).all()
        elif check_admin_permission():
            serial_details = MultiGRNSerialDetails.query.all()
        else:
            user_batches = MultiGRNBatch.query.filter_by(user_id=current_user.id).all()
            batch_ids = [b.id for b in user_batches]
            po_links = MultiGRNPOLink.query.filter(MultiGRNPOLink.batch_id.in_(batch_ids)).all()
            po_link_ids = [link.id for link in po_links]
            line_selections = MultiGRNLineSelection.query.filter(MultiGRNLineSelection.po_link_id.in_(po_link_ids)).all()
            line_selection_ids = [line.id for line in line_selections]
            serial_details = MultiGRNSerialDetails.query.filter(MultiGRNSerialDetails.line_selection_id.in_(line_selection_ids)).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(detail) for detail in serial_details],
            'count': len(serial_details)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-serial-details/<int:detail_id>', methods=['GET'])
@require_permission('multiple_grn')
@login_required
def api_get_multi_grn_serial_detail(detail_id):
    """GET single multi GRN serial detail - Owner or admin only"""
    try:
        serial_detail = MultiGRNSerialDetails.query.get(detail_id)
        if not serial_detail:
            return jsonify({'success': False, 'error': 'Serial detail not found'}), 404
        
        if not check_resource_ownership(serial_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view serial details from your own batches'
            }), 403
        
        return jsonify({'success': True, 'data': serialize_model(serial_detail)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-serial-details', methods=['POST'])
@require_permission('multiple_grn')
@login_required
def api_create_multi_grn_serial_detail():
    """POST create new multi GRN serial detail"""
    try:
        data = get_request_data()
        
        line_selection_id = data.get('line_selection_id')
        if not line_selection_id:
            return jsonify({'success': False, 'error': 'line_selection_id is required'}), 400
        
        line_selection = MultiGRNLineSelection.query.get(line_selection_id)
        if not line_selection:
            return jsonify({'success': False, 'error': 'Line selection not found'}), 404
        
        if not check_resource_ownership(line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only add serial details to your own batches'
            }), 403
        
        serial_detail = MultiGRNSerialDetails(
            line_selection_id=line_selection_id,
            serial_number=data.get('serial_number'),
            manufacturer_serial_number=data.get('manufacturer_serial_number'),
            internal_serial_number=data.get('internal_serial_number'),
            expiry_date=data.get('expiry_date'),
            barcode=data.get('barcode'),
            grn_number=data.get('grn_number'),
            qty_per_pack=data.get('qty_per_pack', 1),
            no_of_packs=data.get('no_of_packs', 1)
        )
        db.session.add(serial_detail)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(serial_detail),
            'message': 'Serial detail created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-serial-details/<int:detail_id>', methods=['PATCH'])
@require_permission('multiple_grn')
@login_required
def api_update_multi_grn_serial_detail(detail_id):
    """PATCH update multi GRN serial detail - Owner or admin only"""
    try:
        serial_detail = MultiGRNSerialDetails.query.get(detail_id)
        if not serial_detail:
            return jsonify({'success': False, 'error': 'Serial detail not found'}), 404
        
        if not check_resource_ownership(serial_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update serial details from your own batches'
            }), 403
        
        data = get_request_data()
        allowed_fields = ['serial_number', 'manufacturer_serial_number', 'internal_serial_number',
                         'expiry_date', 'barcode', 'grn_number', 'qty_per_pack', 'no_of_packs']
        
        for key, value in data.items():
            if key in allowed_fields:
                setattr(serial_detail, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(serial_detail),
            'message': 'Serial detail updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/multi-grn-serial-details/<int:detail_id>', methods=['DELETE'])
@require_permission('multiple_grn')
@login_required
def api_delete_multi_grn_serial_detail(detail_id):
    """DELETE multi GRN serial detail - Owner or admin only"""
    try:
        serial_detail = MultiGRNSerialDetails.query.get(detail_id)
        if not serial_detail:
            return jsonify({'success': False, 'error': 'Serial detail not found'}), 404
        
        if not check_resource_ownership(serial_detail.line_selection.po_link.batch):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete serial details from your own batches'
            }), 403
        
        db.session.delete(serial_detail)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Serial detail deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Delivery Document API Endpoints
# ================================

@app.route('/api/rest/delivery-documents', methods=['GET'])
@login_required
@require_permission('sales_delivery')
def api_get_delivery_documents():
    """GET list of delivery documents - Filtered by ownership"""
    try:
        if check_admin_permission():
            deliveries = DeliveryDocument.query.all()
        else:
            deliveries = DeliveryDocument.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(d) for d in deliveries],
            'count': len(deliveries)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/delivery-documents/<int:delivery_id>', methods=['GET'])
@login_required
@require_permission('sales_delivery')
def api_get_delivery_document(delivery_id):
    """GET single delivery document with items - Owner or admin only"""
    try:
        delivery = DeliveryDocument.query.get(delivery_id)
        if not delivery:
            return jsonify({'success': False, 'error': 'Delivery document not found'}), 404
        
        if not check_resource_ownership(delivery):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own delivery documents'
            }), 403
        
        data = serialize_model(delivery)
        data['items'] = [serialize_model(item) for item in delivery.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/delivery-documents', methods=['POST'])
@login_required
@require_permission('sales_delivery')
def api_create_delivery_document():
    """POST create new delivery document"""
    try:
        data = get_request_data()
        
        delivery = DeliveryDocument(
            so_doc_entry=data.get('so_doc_entry'),
            card_code=data.get('card_code'),
            card_name=data.get('card_name'),
            user_id=current_user.id,
            status=data.get('status', 'draft')
        )
        db.session.add(delivery)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(delivery),
            'message': 'Delivery document created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/delivery-documents/<int:delivery_id>', methods=['PATCH'])
@login_required
@require_permission('sales_delivery')
def api_update_delivery_document(delivery_id):
    """PATCH update delivery document - Owner or admin only"""
    try:
        delivery = DeliveryDocument.query.get(delivery_id)
        if not delivery:
            return jsonify({'success': False, 'error': 'Delivery document not found'}), 404
        
        if not check_resource_ownership(delivery):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own delivery documents'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(delivery, key):
                setattr(delivery, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(delivery),
            'message': 'Delivery document updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/delivery-documents/<int:delivery_id>', methods=['DELETE'])
@login_required
@require_permission('sales_delivery')
def api_delete_delivery_document(delivery_id):
    """DELETE delivery document - Owner or admin only"""
    try:
        delivery = DeliveryDocument.query.get(delivery_id)
        if not delivery:
            return jsonify({'success': False, 'error': 'Delivery document not found'}), 404
        
        if not check_resource_ownership(delivery):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own delivery documents'
            }), 403
        
        db.session.delete(delivery)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Delivery document deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Serial Number Transfer API Endpoints
# ================================

@app.route('/api/rest/serial-transfers', methods=['GET'])
@login_required
@require_permission('serial_transfer')
def api_get_serial_transfers():
    """GET list of serial number transfers"""
    try:
        transfers = SerialNumberTransfer.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(t) for t in transfers],
            'count': len(transfers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-transfers/<int:transfer_id>', methods=['GET'])
@login_required
@require_permission('serial_transfer')
def api_get_serial_transfer(transfer_id):
    """GET single serial number transfer with items"""
    try:
        transfer = SerialNumberTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial transfer not found'}), 404
        
        data = serialize_model(transfer)
        data['items'] = [serialize_model(item) for item in transfer.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-transfers', methods=['POST'])
@login_required
@require_permission('serial_transfer')
def api_create_serial_transfer():
    """POST create new serial number transfer"""
    try:
        data = get_request_data()
        
        transfer = SerialNumberTransfer(
            transfer_number=data.get('transfer_number'),
            user_id=current_user.id,
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            status=data.get('status', 'draft')
        )
        db.session.add(transfer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Serial transfer created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-transfers/<int:transfer_id>', methods=['PATCH'])
@login_required
@require_permission('serial_transfer')
def api_update_serial_transfer(transfer_id):
    """PATCH update serial number transfer"""
    try:
        transfer = SerialNumberTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial transfer not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(transfer, key):
                setattr(transfer, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Serial transfer updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-transfers/<int:transfer_id>', methods=['DELETE'])
@login_required
@require_permission('serial_transfer')
def api_delete_serial_transfer(transfer_id):
    """DELETE serial number transfer"""
    try:
        transfer = SerialNumberTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial transfer not found'}), 404
        
        db.session.delete(transfer)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Serial transfer deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Direct Inventory Transfer API Endpoints
# ================================

@app.route('/api/rest/direct-transfers', methods=['GET'])
@login_required
@require_permission('direct_inventory_transfer')
def api_get_direct_transfers():
    """GET list of direct inventory transfers"""
    try:
        transfers = DirectInventoryTransfer.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(t) for t in transfers],
            'count': len(transfers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/direct-transfers/<int:transfer_id>', methods=['GET'])
@login_required
@require_permission('direct_inventory_transfer')
def api_get_direct_transfer(transfer_id):
    """GET single direct inventory transfer with items"""
    try:
        transfer = DirectInventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Direct transfer not found'}), 404
        
        data = serialize_model(transfer)
        data['items'] = [serialize_model(item) for item in transfer.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/direct-transfers', methods=['POST'])
@login_required
@require_permission('direct_inventory_transfer')
def api_create_direct_transfer():
    """POST create new direct inventory transfer"""
    try:
        data = get_request_data()
        
        transfer = DirectInventoryTransfer(
            transfer_number=data.get('transfer_number'),
            user_id=current_user.id,
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            status=data.get('status', 'draft')
        )
        db.session.add(transfer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Direct transfer created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/direct-transfers/<int:transfer_id>', methods=['PATCH'])
@login_required
@require_permission('direct_inventory_transfer')
def api_update_direct_transfer(transfer_id):
    """PATCH update direct inventory transfer"""
    try:
        transfer = DirectInventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Direct transfer not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(transfer, key):
                setattr(transfer, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Direct transfer updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/direct-transfers/<int:transfer_id>', methods=['DELETE'])
@login_required
@require_permission('direct_inventory_transfer')
def api_delete_direct_transfer(transfer_id):
    """DELETE direct inventory transfer"""
    try:
        transfer = DirectInventoryTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Direct transfer not found'}), 404
        
        db.session.delete(transfer)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Direct transfer deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# QR Code Label API Endpoints
# ================================

@app.route('/api/rest/qr-labels', methods=['GET'])
@login_required
def api_get_qr_labels():
    """GET list of QR code labels"""
    try:
        labels = QRCodeLabel.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(l) for l in labels],
            'count': len(labels)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/qr-labels/<int:label_id>', methods=['GET'])
@login_required
def api_get_qr_label(label_id):
    """GET single QR code label"""
    try:
        label = QRCodeLabel.query.get(label_id)
        if not label:
            return jsonify({'success': False, 'error': 'QR label not found'}), 404
        
        return jsonify({'success': True, 'data': serialize_model(label)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/qr-labels', methods=['POST'])
@login_required
def api_create_qr_label():
    """POST create new QR code label"""
    try:
        data = get_request_data()
        
        label = QRCodeLabel(
            label_type=data.get('label_type'),
            item_code=data.get('item_code'),
            item_name=data.get('item_name'),
            qr_content=data.get('qr_content'),
            user_id=current_user.id
        )
        db.session.add(label)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(label),
            'message': 'QR label created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/qr-labels/<int:label_id>', methods=['PATCH'])
@login_required
def api_update_qr_label(label_id):
    """PATCH update QR code label"""
    try:
        label = QRCodeLabel.query.get(label_id)
        if not label:
            return jsonify({'success': False, 'error': 'QR label not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(label, key):
                setattr(label, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(label),
            'message': 'QR label updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/qr-labels/<int:label_id>', methods=['DELETE'])
@login_required
def api_delete_qr_label(label_id):
    """DELETE QR code label"""
    try:
        label = QRCodeLabel.query.get(label_id)
        if not label:
            return jsonify({'success': False, 'error': 'QR label not found'}), 404
        
        db.session.delete(label)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'QR label deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# SAP Inventory Count API Endpoints
# ================================

@app.route('/api/rest/sap-inventory-counts', methods=['GET'])
@login_required
@require_permission('inventory_counting')
def api_get_sap_inventory_counts():
    """GET list of SAP inventory counts"""
    try:
        counts = SAPInventoryCount.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(c) for c in counts],
            'count': len(counts)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/sap-inventory-counts/<int:count_id>', methods=['GET'])
@login_required
@require_permission('inventory_counting')
def api_get_sap_inventory_count(count_id):
    """GET single SAP inventory count with lines"""
    try:
        count = SAPInventoryCount.query.get(count_id)
        if not count:
            return jsonify({'success': False, 'error': 'SAP inventory count not found'}), 404
        
        data = serialize_model(count)
        data['lines'] = [serialize_model(line) for line in count.lines]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/sap-inventory-counts/<int:count_id>', methods=['PATCH'])
@login_required
@require_permission('inventory_counting')
def api_update_sap_inventory_count(count_id):
    """PATCH update SAP inventory count"""
    try:
        count = SAPInventoryCount.query.get(count_id)
        if not count:
            return jsonify({'success': False, 'error': 'SAP inventory count not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(count, key):
                setattr(count, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(count),
            'message': 'SAP inventory count updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Serial Item Transfer API Endpoints
# ================================

@app.route('/api/rest/serial-item-transfers', methods=['GET'])
@login_required
@require_permission('serial_item_transfer')
def api_get_serial_item_transfers():
    """GET list of serial item transfers - Filtered by ownership"""
    try:
        if check_admin_permission():
            transfers = SerialItemTransfer.query.all()
        else:
            transfers = SerialItemTransfer.query.filter_by(user_id=current_user.id).all()
        
        return jsonify({
            'success': True,
            'data': [serialize_model(t) for t in transfers],
            'count': len(transfers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfers/<int:transfer_id>', methods=['GET'])
@login_required
@require_permission('serial_item_transfer')
def api_get_serial_item_transfer(transfer_id):
    """GET single serial item transfer with items - Owner or admin only"""
    try:
        transfer = SerialItemTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial item transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only view your own serial item transfers'
            }), 403
        
        data = serialize_model(transfer)
        data['items'] = [serialize_model(item) for item in transfer.items]
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfers', methods=['POST'])
@login_required
@require_permission('serial_item_transfer')
def api_create_serial_item_transfer():
    """POST create new serial item transfer"""
    try:
        data = get_request_data()
        
        transfer = SerialItemTransfer(
            transfer_number=data.get('transfer_number'),
            user_id=current_user.id,
            status=data.get('status', 'draft'),
            from_warehouse=data.get('from_warehouse'),
            to_warehouse=data.get('to_warehouse'),
            priority=data.get('priority', 'normal'),
            notes=data.get('notes')
        )
        db.session.add(transfer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Serial item transfer created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfers/<int:transfer_id>', methods=['PATCH'])
@login_required
@require_permission('serial_item_transfer')
def api_update_serial_item_transfer(transfer_id):
    """PATCH update serial item transfer - Owner or admin only"""
    try:
        transfer = SerialItemTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial item transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only update your own serial item transfers'
            }), 403
        
        data = get_request_data()
        for key, value in data.items():
            if key != 'items' and hasattr(transfer, key):
                setattr(transfer, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(transfer),
            'message': 'Serial item transfer updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfers/<int:transfer_id>', methods=['DELETE'])
@login_required
@require_permission('serial_item_transfer')
def api_delete_serial_item_transfer(transfer_id):
    """DELETE serial item transfer - Owner or admin only"""
    try:
        transfer = SerialItemTransfer.query.get(transfer_id)
        if not transfer:
            return jsonify({'success': False, 'error': 'Serial item transfer not found'}), 404
        
        if not check_resource_ownership(transfer):
            return jsonify({
                'success': False,
                'error': 'Access denied: You can only delete your own serial item transfers'
            }), 403
        
        db.session.delete(transfer)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Serial item transfer deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# Serial Item Transfer Items API Endpoints
# ================================

@app.route('/api/rest/serial-item-transfer-items', methods=['GET'])
@login_required
@require_permission('serial_item_transfer')
def api_get_serial_item_transfer_items():
    """GET list of all serial item transfer items - Permission required"""
    try:
        items = SerialItemTransferItem.query.all()
        return jsonify({
            'success': True,
            'data': [serialize_model(item) for item in items],
            'count': len(items)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfer-items/<int:item_id>', methods=['GET'])
@login_required
@require_permission('serial_item_transfer')
def api_get_serial_item_transfer_item(item_id):
    """GET single serial item transfer item"""
    try:
        item = SerialItemTransferItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'Serial item transfer item not found'}), 404
        
        return jsonify({'success': True, 'data': serialize_model(item)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfer-items', methods=['POST'])
@login_required
@require_permission('serial_item_transfer')
def api_create_serial_item_transfer_item():
    """POST create new serial item transfer item"""
    try:
        data = get_request_data()
        
        item = SerialItemTransferItem(
            serial_item_transfer_id=data.get('serial_item_transfer_id'),
            serial_number=data.get('serial_number'),
            item_code=data.get('item_code'),
            item_description=data.get('item_description'),
            warehouse_code=data.get('warehouse_code'),
            quantity=data.get('quantity', 1),
            unit_of_measure=data.get('unit_of_measure', 'EA'),
            from_warehouse_code=data.get('from_warehouse_code'),
            to_warehouse_code=data.get('to_warehouse_code'),
            qc_status=data.get('qc_status', 'pending'),
            validation_status=data.get('validation_status', 'pending'),
            validation_error=data.get('validation_error')
        )
        db.session.add(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': serialize_model(item),
            'message': 'Serial item transfer item created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfer-items/<int:item_id>', methods=['PATCH'])
@login_required
@require_permission('serial_item_transfer')
def api_update_serial_item_transfer_item(item_id):
    """PATCH update serial item transfer item"""
    try:
        item = SerialItemTransferItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'Serial item transfer item not found'}), 404
        
        data = get_request_data()
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'data': serialize_model(item),
            'message': 'Serial item transfer item updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/rest/serial-item-transfer-items/<int:item_id>', methods=['DELETE'])
@login_required
@require_permission('serial_item_transfer')
def api_delete_serial_item_transfer_item(item_id):
    """DELETE serial item transfer item"""
    try:
        item = SerialItemTransferItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'Serial item transfer item not found'}), 404
        
        db.session.delete(item)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Serial item transfer item deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
