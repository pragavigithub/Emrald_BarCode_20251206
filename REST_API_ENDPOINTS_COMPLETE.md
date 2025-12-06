# Complete REST API Endpoints Documentation

## Authentication Endpoints

### Login
**POST** `/api/rest/auth/login`
- **Description**: Authenticate user and create session
- **Authentication**: None (public endpoint)
- **Request Body**:
```json
{
  "username": "admin",
  "password": "yourpassword"
}
```
- **Success Response** (200):
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "is_active": true,
      ...
    },
    "permissions": {
      "dashboard": true,
      "grpo": true,
      ...
    }
  }
}
```
- **Error Response** (401):
```json
{
  "success": false,
  "error": "Invalid username or password"
}
```

### Logout
**POST** `/api/rest/auth/logout`
- **Description**: Invalidate user session
- **Authentication**: Required (login_required)
- **Success Response** (200):
```json
{
  "success": true,
  "message": "Logout successful"
}
```

### Get Current User
**GET** `/api/rest/auth/me`
- **Description**: Get authenticated user information
- **Authentication**: Required (login_required)
- **Success Response** (200):
```json
{
  "success": true,
  "data": {
    "user": {
      "id": 1,
      "username": "admin",
      ...
    },
    "permissions": {
      "dashboard": true,
      ...
    }
  }
}
```

---

## User Management Endpoints

### List Users
**GET** `/api/rest/users`
- **Authentication**: Required (admin only)
- **Success Response**: Returns array of all users

### Get User by ID
**GET** `/api/rest/users/<user_id>`
- **Authentication**: Required (admin or self)
- **Success Response**: Returns single user object

### Create User
**POST** `/api/rest/users`
- **Authentication**: Required (admin only)
- **Request Body**:
```json
{
  "username": "newuser",
  "email": "user@example.com",
  "password": "password123",
  "first_name": "John",
  "last_name": "Doe",
  "role": "user",
  "branch_id": "01",
  "branch_name": "Main Branch",
  "is_active": true
}
```

### Update User
**PATCH** `/api/rest/users/<user_id>`
- **Authentication**: Required (admin or self with limited fields)

### Delete User
**DELETE** `/api/rest/users/<user_id>`
- **Authentication**: Required (admin only)

---

## Inventory Transfer Endpoints

### List Inventory Transfers
**GET** `/api/rest/inventory-transfers`
- **Authentication**: Required (permission: inventory_transfer)
- **Filter**: Non-admin users see only their own transfers

### Get Inventory Transfer
**GET** `/api/rest/inventory-transfers/<transfer_id>`
- **Authentication**: Required (permission: inventory_transfer)
- **Authorization**: Owner or admin only

### Create Inventory Transfer
**POST** `/api/rest/inventory-transfers`
- **Authentication**: Required (permission: inventory_transfer)
- **Request Body**:
```json
{
  "transfer_request_number": "TR-001",
  "from_warehouse": "WH01",
  "to_warehouse": "WH02",
  "status": "draft"
}
```

### Update Inventory Transfer
**PATCH** `/api/rest/inventory-transfers/<transfer_id>`
- **Authentication**: Required (permission: inventory_transfer)
- **Authorization**: Owner or admin only

### Delete Inventory Transfer
**DELETE** `/api/rest/inventory-transfers/<transfer_id>`
- **Authentication**: Required (permission: inventory_transfer)
- **Authorization**: Owner or admin only

---

## Pick List Endpoints

### List Pick Lists
**GET** `/api/rest/pick-lists`
- **Authentication**: Required (permission: pick_list)

### Get Pick List
**GET** `/api/rest/pick-lists/<pick_list_id>`
- **Authentication**: Required (permission: pick_list)

### Create Pick List
**POST** `/api/rest/pick-lists`
- **Authentication**: Required (permission: pick_list)

### Update Pick List
**PATCH** `/api/rest/pick-lists/<pick_list_id>`
- **Authentication**: Required (permission: pick_list)

### Delete Pick List
**DELETE** `/api/rest/pick-lists/<pick_list_id>`
- **Authentication**: Required (permission: pick_list)

---

## Inventory Count Endpoints

### List Inventory Counts
**GET** `/api/rest/inventory-counts`
- **Authentication**: Required (permission: inventory_counting)

### Get Inventory Count
**GET** `/api/rest/inventory-counts/<count_id>`
- **Authentication**: Required (permission: inventory_counting)

### Create Inventory Count
**POST** `/api/rest/inventory-counts`
- **Authentication**: Required (permission: inventory_counting)

### Update Inventory Count
**PATCH** `/api/rest/inventory-counts/<count_id>`
- **Authentication**: Required (permission: inventory_counting)

### Delete Inventory Count
**DELETE** `/api/rest/inventory-counts/<count_id>`
- **Authentication**: Required (permission: inventory_counting)

---

## GRPO (Goods Receipt PO) Endpoints

### List GRPO Documents
**GET** `/api/rest/grpo-documents`
- **Authentication**: Required (permission: grpo)

### Get GRPO Document
**GET** `/api/rest/grpo-documents/<doc_id>`
- **Authentication**: Required (permission: grpo)

### Create GRPO Document
**POST** `/api/rest/grpo-documents`
- **Authentication**: Required (permission: grpo)

### Update GRPO Document
**PATCH** `/api/rest/grpo-documents/<doc_id>`
- **Authentication**: Required (permission: grpo)

### Delete GRPO Document
**DELETE** `/api/rest/grpo-documents/<doc_id>`
- **Authentication**: Required (permission: grpo)

### List GRPO Items
**GET** `/api/rest/grpo-items`
- **Authentication**: Required (permission: grpo)

### Get GRPO Item
**GET** `/api/rest/grpo-items/<item_id>`
- **Authentication**: Required (permission: grpo)

### Create GRPO Item
**POST** `/api/rest/grpo-items`
- **Authentication**: Required (permission: grpo)

### Update GRPO Item
**PATCH** `/api/rest/grpo-items/<item_id>`
- **Authentication**: Required (permission: grpo)

### Delete GRPO Item
**DELETE** `/api/rest/grpo-items/<item_id>`
- **Authentication**: Required (permission: grpo)

---

## Multi GRN Batch Endpoints

### List Multi GRN Batches
**GET** `/api/rest/multi-grn-batches`
- **Authentication**: Required (permission: multiple_grn)

### Get Multi GRN Batch
**GET** `/api/rest/multi-grn-batches/<batch_id>`
- **Authentication**: Required (permission: multiple_grn)

### Create Multi GRN Batch
**POST** `/api/rest/multi-grn-batches`
- **Authentication**: Required (permission: multiple_grn)

### Update Multi GRN Batch
**PATCH** `/api/rest/multi-grn-batches/<batch_id>`
- **Authentication**: Required (permission: multiple_grn)

### Delete Multi GRN Batch
**DELETE** `/api/rest/multi-grn-batches/<batch_id>`
- **Authentication**: Required (permission: multiple_grn)

---

## Delivery Document Endpoints

### List Delivery Documents
**GET** `/api/rest/delivery-documents`
- **Authentication**: Required (permission: sales_delivery)

### Get Delivery Document
**GET** `/api/rest/delivery-documents/<delivery_id>`
- **Authentication**: Required (permission: sales_delivery)

### Create Delivery Document
**POST** `/api/rest/delivery-documents`
- **Authentication**: Required (permission: sales_delivery)

### Update Delivery Document
**PATCH** `/api/rest/delivery-documents/<delivery_id>`
- **Authentication**: Required (permission: sales_delivery)

### Delete Delivery Document
**DELETE** `/api/rest/delivery-documents/<delivery_id>`
- **Authentication**: Required (permission: sales_delivery)

---

## Serial Number Transfer Endpoints

### List Serial Transfers
**GET** `/api/rest/serial-transfers`
- **Authentication**: Required (permission: serial_transfer)

### Get Serial Transfer
**GET** `/api/rest/serial-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_transfer)

### Create Serial Transfer
**POST** `/api/rest/serial-transfers`
- **Authentication**: Required (permission: serial_transfer)

### Update Serial Transfer
**PATCH** `/api/rest/serial-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_transfer)

### Delete Serial Transfer
**DELETE** `/api/rest/serial-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_transfer)

---

## Serial Item Transfer Endpoints (NEW)

### List Serial Item Transfers
**GET** `/api/rest/serial-item-transfers`
- **Authentication**: Required (permission: serial_item_transfer)
- **Filter**: Non-admin users see only their own transfers

### Get Serial Item Transfer
**GET** `/api/rest/serial-item-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_item_transfer)
- **Authorization**: Owner or admin only
- **Response**: Includes nested items array

### Create Serial Item Transfer
**POST** `/api/rest/serial-item-transfers`
- **Authentication**: Required (permission: serial_item_transfer)
- **Request Body**:
```json
{
  "transfer_number": "SIT-001",
  "from_warehouse": "WH01",
  "to_warehouse": "WH02",
  "priority": "normal",
  "notes": "Serial item transfer"
}
```

### Update Serial Item Transfer
**PATCH** `/api/rest/serial-item-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_item_transfer)
- **Authorization**: Owner or admin only

### Delete Serial Item Transfer
**DELETE** `/api/rest/serial-item-transfers/<transfer_id>`
- **Authentication**: Required (permission: serial_item_transfer)
- **Authorization**: Owner or admin only

---

## Serial Item Transfer Items Endpoints (NEW)

### List Serial Item Transfer Items
**GET** `/api/rest/serial-item-transfer-items`
- **Authentication**: Required (permission: serial_item_transfer)

### Get Serial Item Transfer Item
**GET** `/api/rest/serial-item-transfer-items/<item_id>`
- **Authentication**: Required (permission: serial_item_transfer)

### Create Serial Item Transfer Item
**POST** `/api/rest/serial-item-transfer-items`
- **Authentication**: Required (permission: serial_item_transfer)
- **Request Body**:
```json
{
  "serial_item_transfer_id": 1,
  "serial_number": "SN123456",
  "item_code": "ITEM001",
  "item_description": "Sample Item",
  "warehouse_code": "WH01",
  "quantity": 1,
  "from_warehouse_code": "WH01",
  "to_warehouse_code": "WH02",
  "qc_status": "pending",
  "validation_status": "pending"
}
```

### Update Serial Item Transfer Item
**PATCH** `/api/rest/serial-item-transfer-items/<item_id>`
- **Authentication**: Required (permission: serial_item_transfer)

### Delete Serial Item Transfer Item
**DELETE** `/api/rest/serial-item-transfer-items/<item_id>`
- **Authentication**: Required (permission: serial_item_transfer)

---

## Direct Transfer Endpoints

### List Direct Transfers
**GET** `/api/rest/direct-transfers`
- **Authentication**: Required (permission: direct_inventory_transfer)

### Get Direct Transfer
**GET** `/api/rest/direct-transfers/<transfer_id>`
- **Authentication**: Required (permission: direct_inventory_transfer)

### Create Direct Transfer
**POST** `/api/rest/direct-transfers`
- **Authentication**: Required (permission: direct_inventory_transfer)

### Update Direct Transfer
**PATCH** `/api/rest/direct-transfers/<transfer_id>`
- **Authentication**: Required (permission: direct_inventory_transfer)

### Delete Direct Transfer
**DELETE** `/api/rest/direct-transfers/<transfer_id>`
- **Authentication**: Required (permission: direct_inventory_transfer)

---

## QR Label Endpoints

### List QR Labels
**GET** `/api/rest/qr-labels`
- **Authentication**: Required (login_required)

### Get QR Label
**GET** `/api/rest/qr-labels/<label_id>`
- **Authentication**: Required (login_required)

### Create QR Label
**POST** `/api/rest/qr-labels`
- **Authentication**: Required (login_required)

### Update QR Label
**PATCH** `/api/rest/qr-labels/<label_id>`
- **Authentication**: Required (login_required)

### Delete QR Label
**DELETE** `/api/rest/qr-labels/<label_id>`
- **Authentication**: Required (login_required)

---

## Bin Location Endpoints

### List Bin Locations
**GET** `/api/rest/bin-locations`
- **Authentication**: Required (login_required)

### Get Bin Location
**GET** `/api/rest/bin-locations/<bin_id>`
- **Authentication**: Required (login_required)

### Create Bin Location
**POST** `/api/rest/bin-locations`
- **Authentication**: Required (admin only)

### Update Bin Location
**PATCH** `/api/rest/bin-locations/<bin_id>`
- **Authentication**: Required (admin only)

### Delete Bin Location
**DELETE** `/api/rest/bin-locations/<bin_id>`
- **Authentication**: Required (admin only)

---

## SAP Inventory Count Endpoints

### List SAP Inventory Counts
**GET** `/api/rest/sap-inventory-counts`
- **Authentication**: Required (permission: inventory_counting)

### Get SAP Inventory Count
**GET** `/api/rest/sap-inventory-counts/<count_id>`
- **Authentication**: Required (permission: inventory_counting)
- **Response**: Includes nested lines array

### Update SAP Inventory Count
**PATCH** `/api/rest/sap-inventory-counts/<count_id>`
- **Authentication**: Required (permission: inventory_counting)

---

## Security & Authorization

### Authentication Flow
1. **Login**: POST to `/api/rest/auth/login` with username and password
2. **Session**: Server creates session cookie (Flask-Login)
3. **Subsequent Requests**: Include session cookie in all requests
4. **Logout**: POST to `/api/rest/auth/logout` to invalidate session

### Authorization Levels
1. **Public**: No authentication required (only /auth/login)
2. **Login Required**: Must be authenticated
3. **Permission Required**: Must have specific permission
4. **Admin Only**: Must have admin role
5. **Owner or Admin**: Must own resource or be admin

### Response Format
All endpoints follow a consistent JSON response format:

**Success Response**:
```json
{
  "success": true,
  "data": { ... },
  "message": "Optional success message"
}
```

**Error Response**:
```json
{
  "success": false,
  "error": "Error message description"
}
```

### HTTP Status Codes
- **200**: Success
- **201**: Created (POST endpoints)
- **400**: Bad Request
- **401**: Unauthorized (invalid credentials)
- **403**: Forbidden (insufficient permissions)
- **404**: Not Found
- **500**: Internal Server Error

---

## Testing Examples

### Example 1: Login and Get Users

```bash
# Login
curl -X POST http://localhost:5000/api/rest/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword"}' \
  -c cookies.txt

# Get users (using session cookie)
curl -X GET http://localhost:5000/api/rest/users \
  -b cookies.txt
```

### Example 2: Create Inventory Transfer

```bash
# Create transfer
curl -X POST http://localhost:5000/api/rest/inventory-transfers \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "transfer_request_number": "TR-001",
    "from_warehouse": "WH01",
    "to_warehouse": "WH02",
    "status": "draft"
  }'
```

### Example 3: Get Current User Info

```bash
# Get authenticated user
curl -X GET http://localhost:5000/api/rest/auth/me \
  -b cookies.txt
```

---

## Notes

- **NEW**: Authentication endpoints (login, logout, get current user)
- **NEW**: Serial Item Transfer endpoints (complete CRUD)
- **NEW**: Serial Item Transfer Items endpoints (complete CRUD)
- All endpoints return JSON responses
- All endpoints use proper RBAC (Role-Based Access Control)
- Ownership checks ensure users can only access their own data (except admins)
- Consistent error handling across all endpoints
