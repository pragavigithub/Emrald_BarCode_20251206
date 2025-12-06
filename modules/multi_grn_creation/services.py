"""
SAP B1 Service Layer integration for Multiple GRN Creation
Provides methods to interact with SAP B1 APIs for customer, PO, and GRN creation
"""
import logging
import requests
import json
from datetime import datetime
import os
from flask import current_app
import urllib.parse
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SAPMultiGRNService:
    """Service class for SAP B1 integration specific to Multiple GRN Creation"""
    
    def __init__(self):
        self.base_url = os.environ.get('SAP_B1_SERVER', '')
        self.username = os.environ.get('SAP_B1_USERNAME', '')
        self.password = os.environ.get('SAP_B1_PASSWORD', '')
        self.company_db = os.environ.get('SAP_B1_COMPANY_DB', '')
        self.session_id = None
        self.session = requests.Session()
        self.session.verify = False  # For development, in production use proper SSL
        self.is_offline = False
        self.enable_mock_data = os.environ.get('ENABLE_MOCK_SAP_DATA', 'false').lower() == 'true'

        

    
    def login(self):
        """Login to SAP B1 Service Layer"""
        if not all([self.base_url, self.username, self.password, self.company_db]):
            logging.warning("⚠️ SAP B1 configuration incomplete. Please check environment variables.")
            logging.warning(f"   SAP_B1_SERVER: {'✓' if self.base_url else '✗'}")
            logging.warning(f"   SAP_B1_USERNAME: {'✓' if self.username else '✗'}")
            logging.warning(f"   SAP_B1_PASSWORD: {'✓' if self.password else '✗'}")
            logging.warning(f"   SAP_B1_COMPANY_DB: {'✓' if self.company_db else '✗'}")
            return False
        
        login_url = f"{self.base_url}/b1s/v1/Login"
        login_data = {
            "UserName": self.username,
            "Password": self.password,
            "CompanyDB": self.company_db
        }
        
        try:
            logging.info(f"🔐 Attempting SAP login to {self.base_url}...")
            response = self.session.post(login_url, json=login_data, timeout=30)
            if response.status_code == 200:
                self.session_id = response.json().get('SessionId')
                logging.info("✅ SAP B1 login successful"+self.session_id)
                logging.info("✅ SAP B1 login successful")
                return True
            else:
                logging.warning(f"❌ SAP B1 login failed (Status {response.status_code}): {response.text}")
                logging.error(f"❌ SAP B1 login failed (Status {response.status_code}): {response.text}")
                return False
        except requests.exceptions.ConnectionError as e:
            logging.error(f"❌ SAP B1 connection failed: Cannot reach {self.base_url}")
            logging.error(f"❌ SAP B1 connection failed: Cannot reach {self.base_url}")
            logging.error(f"   This may be a network issue or the SAP server may not be accessible from Replit")
            logging.error(f"   Error details: {str(e)}")
            return False
        except requests.exceptions.Timeout:
            logging.error(f"❌ SAP B1 login timeout: Server did not respond within 30 seconds")
            return False
        except Exception as e:
            logging.error(f"❌ SAP B1 login error: {str(e)}")
            return False
    
    def ensure_logged_in(self):
        """Ensure we have a valid session, login if needed"""
        if not self.session_id:
            return self.login()
        return True
    
    def fetch_business_partners(self, card_type='S'):
        """
        Fetch valid Business Partners (Suppliers/Customers)
        card_type: 'S' for Suppliers, 'C' for Customers
        """
        if not self.ensure_logged_in():
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            filter_query = f"Valid eq 'tYES' and CardType eq '{card_type}'"
            url = f"{self.base_url}/b1s/v1/BusinessPartners"
            params = {
                '$filter': filter_query,
                '$select': 'CardCode,CardName,Valid,CardType'
            }
            headers = {'Prefer': 'odata.maxpagesize=0'}
            
            response = self.session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                partners = data.get('value', [])
                logging.info(f"✅ Fetched {len(partners)} business partners")
                return {'success': True, 'partners': partners}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_business_partners(card_type)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                logging.error(f"❌ Failed to fetch business partners: {response.text}")
                return {'success': False, 'error': response.text}
                
        except Exception as e:
            logging.error(f"❌ Error fetching business partners: {str(e)}")
            return {'success': False, 'error': str(e)}

    def fetch_all_valid_customers(self):
            """Fetch all valid Business Partners for dropdown display"""
            if self.enable_mock_data:
                logging.info("📋 Using mock customer data (ENABLE_MOCK_SAP_DATA=true)")
                return self.get_mock_customers()
            
            if not self.ensure_logged_in():
                error_msg = 'SAP login failed - using mock data as fallback'
                logging.warning(f"⚠️ {error_msg}")
                return self.get_mock_customers()

            try:
                url = f"{self.base_url}/b1s/v1/BusinessPartners"
                params = {
                    '$filter': f"Valid eq 'tYES'",
                    '$select': 'CardCode,CardName,Valid'
                }
                headers = {'Prefer': 'odata.maxpagesize=0'}

                logging.info(f"📡 Fetching BusinessPartners from SAP: {url}")
                response = self.session.get(url, params=params, headers=headers, timeout=30)

                logging.info(f"📊 SAP Response Status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    customers = [
                        {
                            'CardCode': c['CardCode'],
                            'CardName': c['CardName']
                        }
                        for c in data.get('value', [])
                        if c.get('Valid') == 'tYES'
                    ]
                    logging.info(f"✅ Successfully loaded {len(customers)} valid customers from SAP")
                    return {'success': True, 'customers': customers}

                elif response.status_code == 401:
                    self.session_id = None
                    logging.warning("⚠️ Session expired, attempting re-login...")
                    if self.login():
                        return self.fetch_all_valid_customers()
                    return {'success': False, 'error': 'SAP authentication failed - invalid credentials'}

                else:
                    error_msg = f"SAP API error (Status {response.status_code}): {response.text}"
                    logging.error(f"❌ {error_msg}")
                    return {'success': False, 'error': error_msg}

            except requests.exceptions.ConnectionError as e:
                error_msg = f"Cannot connect to SAP server at {self.base_url} - using mock data as fallback"
                logging.warning(f"⚠️ {error_msg}")
                return self.get_mock_customers()
            except requests.exceptions.Timeout:
                error_msg = "SAP request timeout - using mock data as fallback"
                logging.warning(f"⚠️ {error_msg}")
                return self.get_mock_customers()
            except Exception as e:
                error_msg = f"Unexpected error fetching customers - using mock data as fallback: {str(e)}"
                logging.warning(f"⚠️ {error_msg}")
                return self.get_mock_customers()


    
    def fetch_open_purchase_orders_by_name(self, card_name):
        """
        Fetch open Purchase Orders for a specific customer/supplier by CardName
        Returns only POs with DocumentStatus = 'bost_Open' and open line items
        """
        if self.enable_mock_data:
            logging.info(f"📋 Using mock PO data for {card_name} (ENABLE_MOCK_SAP_DATA=true)")
            return self.get_mock_purchase_orders(card_name)
        
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - using mock PO data for {card_name}")
            return self.get_mock_purchase_orders(card_name)
        try:
            url = f"{self.base_url}/b1s/v1/PurchaseOrders"
            params = {
                '$filter': f"CardName eq '{card_name}' and DocumentStatus eq 'bost_Open'",
                '$select': 'DocEntry,DocNum,CardCode,CardName,DocDate,DocDueDate,DocTotal,DocumentStatus,DocumentLines'
            }
            
            logging.info(f"🔍 Fetching open POs for CardName: {card_name}")
            logging.info(f"  SAP URL: {url}?$filter={params['$filter']}")
            response = self.session.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                pos = data.get('value', [])
                open_pos = []
                for po in pos:
                    open_lines = [
                        line for line in po.get('DocumentLines')
                        if line.get('LineStatus') == 'bost_Open' and line.get('Quantity', 0) > 0
                    ]
                    if open_lines:
                        po['OpenLines'] = open_lines
                        po['TotalOpenLines'] = len(open_lines)
                        open_pos.append(po)

                logging.info(f"✅ Fetched {len(open_pos)} open POs for CardName {card_name}")
                return {'success': True, 'purchase_orders': open_pos}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_open_purchase_orders_by_name(card_name)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                logging.warning(f"⚠️ Failed to fetch POs for CardName {card_name} - using mock data: {response.text}")
                return self.get_mock_purchase_orders(card_name)
                
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"⚠️ Cannot connect to SAP - using mock PO data for {card_name}")
            return self.get_mock_purchase_orders(card_name)
        except requests.exceptions.Timeout:
            logging.warning(f"⚠️ SAP request timeout - using mock PO data for {card_name}")
            return self.get_mock_purchase_orders(card_name)
        except Exception as e:
            logging.warning(f"⚠️ Error fetching POs for {card_name} - using mock data: {str(e)}")
            return self.get_mock_purchase_orders(card_name)
    

    
    def create_purchase_delivery_note(self, grn_data):

        
        if not self.ensure_logged_in():
            return {'success': False, 'error': 'SAP login failed - GRN not created'}
        print(grn_data)
        try:
            url = f"{self.base_url}/b1s/v1/PurchaseDeliveryNotes"
            print(grn_data)
            response = self.session.post(url, json=grn_data, timeout=60)
            
            if response.status_code == 201:
                result = response.json()
                doc_entry = result.get('DocEntry')
                doc_num = result.get('DocNum')
                logging.info(f"✅ GRN created successfully: DocNum={doc_num}, DocEntry={doc_entry}")
                return {
                    'success': True,
                    'doc_entry': doc_entry,
                    'doc_num': doc_num,
                    'response': result
                }
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.create_purchase_delivery_note(grn_data)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to create GRN: {error_msg}")
                return {'success': False, 'error': error_msg, 'status_code': response.status_code}

        except Exception as e:
            logging.error(f"❌ Error creating GRN: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_mock_customers(self):
        """Generate mock customer data for testing without SAP connectivity"""
        return {
            'success': True,
            'customers': [
                {'CardCode': 'C10000', 'CardName': 'Acme Corporation'},
                {'CardCode': 'C10001', 'CardName': 'Global Industries Ltd'},
                {'CardCode': 'C10002', 'CardName': 'Tech Solutions Inc'},
                {'CardCode': 'C10003', 'CardName': 'Prime Suppliers Co'},
                {'CardCode': 'C10004', 'CardName': 'Quality Manufacturing'},
                {'CardCode': 'C10005', 'CardName': 'United Trading Company'},
            ]
        }
    
    def get_mock_customers_from_open_pos(self):
        """Generate mock customers from open POs for testing without SAP connectivity"""
        return {
            'success': True,
            'customers': [
                {'CardCode': 'C10000', 'CardName': 'Acme Corporation'},
                {'CardCode': 'C10001', 'CardName': 'Global Industries Ltd'},
                {'CardCode': 'C10002', 'CardName': 'Tech Solutions Inc'},
            ]
        }
    
    def get_mock_cardcodes_by_series(self, series_id=None):
        """Generate mock cardcode data for testing without SAP connectivity"""
        return {
            'success': True,
            'cardcodes': [
                {
                    'CardCode': 'V001504',
                    'CardName': 'SRI SABARI AGENCIES',
                    'DocumentStatus': 'O',
                    'DocNum': 5500181,
                    'Series': int(series_id) if series_id else 987,
                    'DocDate': '2025-12-06',
                    'DocDueDate': '2025-12-06',
                    'DocTotal': 4490.0,
                    'DocEntry': 43267
                },
                {
                    'CardCode': 'V001505',
                    'CardName': 'PRIME SUPPLIERS PVT LTD',
                    'DocumentStatus': 'O',
                    'DocNum': 5500182,
                    'Series': int(series_id) if series_id else 987,
                    'DocDate': '2025-12-05',
                    'DocDueDate': '2025-12-10',
                    'DocTotal': 12500.0,
                    'DocEntry': 43268
                },
                {
                    'CardCode': 'V001506',
                    'CardName': 'TECH COMPONENTS INDIA',
                    'DocumentStatus': 'O',
                    'DocNum': 5500183,
                    'Series': int(series_id) if series_id else 987,
                    'DocDate': '2025-12-04',
                    'DocDueDate': '2025-12-15',
                    'DocTotal': 8750.0,
                    'DocEntry': 43269
                }
            ]
        }
    
    def get_mock_po_lines(self, doc_entry):
        """Generate mock PO line items for testing without SAP connectivity
        Note: LineStatus 'O' is the SAP $crossjoin format, 'bost_Open' is the standard PO format
        """
        document_lines = [
            {
                'LineNum': 0,
                'ItemCode': 'ITEM001',
                'ItemDescription': 'Test Item 1 - Batch Managed',
                'WarehouseCode': 'WH01',
                'UnitsOfMeasurment': 1.0,
                'DocEntry': doc_entry,
                'LineTotal': 1500.0,
                'LineStatus': 'O',
                'Quantity': 10.0,
                'Price': 150.0,
                'PriceAfterVAT': 177.0
            },
            {
                'LineNum': 1,
                'ItemCode': 'ITEM002',
                'ItemDescription': 'Test Item 2 - Serial Managed',
                'WarehouseCode': 'WH01',
                'UnitsOfMeasurment': 1.0,
                'DocEntry': doc_entry,
                'LineTotal': 2990.0,
                'LineStatus': 'O',
                'Quantity': 5.0,
                'Price': 598.0,
                'PriceAfterVAT': 705.64
            }
        ]
        
        return {
            'success': True,
            'purchase_order': {
                'CardCode': 'V001504',
                'CardName': 'SRI SABARI AGENCIES',
                'DocumentStatus': 'O',
                'DocNum': 5500181,
                'Series': 987,
                'DocDate': '2025-12-06',
                'DocDueDate': '2025-12-06',
                'DocTotal': 4490.0,
                'DocEntry': doc_entry,
                'DocumentLines': document_lines,
                'OpenLines': document_lines,
                'TotalOpenLines': len(document_lines)
            }
        }
    
    def validate_item_code(self, item_code):
        """
        Validate item code and get batch/serial management info
        Uses SAP B1 SQLQueries endpoint to check item properties
        """
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - cannot validate item {item_code}")
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            url = f"{self.base_url}/b1s/v1/SQLQueries('ItemCode_Batch_Serial_Val')/List"
            payload = {
                "ParamList": f"itemCode='{item_code}'"
            }
            
            logging.info(f"🔍 Validating item code: {item_code}")
            response = self.session.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('value', [])
                
                if not items:
                    logging.warning(f"⚠️ Item code {item_code} not found in SAP")
                    return {'success': False, 'error': f'Item code {item_code} not found'}
                
                item_data = items[0]
                batch_managed = item_data.get('BatchNum', 'N') == 'Y'
                serial_managed = item_data.get('SerialNum', 'N') == 'Y'
                management_method = item_data.get('NonBatch_NonSerialMethod', 'N')
                
                # Determine inventory type
                if serial_managed:
                    inventory_type = 'serial'
                elif batch_managed:
                    inventory_type = 'batch'
                elif management_method == 'R':
                    inventory_type = 'quantity_based'
                else:
                    inventory_type = 'standard'
                
                logging.info(f"✅ Item {item_code} validated: Type={inventory_type}")
                return {
                    'success': True,
                    'item_code': item_data.get('ItemCode'),
                    'batch_managed': batch_managed,
                    'serial_managed': serial_managed,
                    'inventory_type': inventory_type,
                    'management_method': management_method,
                    'item_data': item_data
                }
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.validate_item_code(item_code)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to validate item {item_code}: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logging.error(f"❌ Error validating item {item_code}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_item_details(self, item_code):
        """
        Fetch item details from SAP B1
        Returns item name, UoM, price, and other details
        """
        if not self.ensure_logged_in():
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            url = f"{self.base_url}/b1s/v1/Items('{item_code}')"
            params = {
                '$select': 'ItemCode,ItemName,InventoryUOM,PurchaseUnit,SalesUnit,QuantityOnStock'
            }
            
            logging.info(f"📦 Fetching item details for: {item_code}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                item_data = response.json()
                logging.info(f"✅ Item details fetched for {item_code}")
                return {
                    'success': True,
                    'item': item_data
                }
            elif response.status_code == 404:
                return {'success': False, 'error': f'Item {item_code} not found'}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.get_item_details(item_code)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                return {'success': False, 'error': response.text}
                
        except Exception as e:
            logging.error(f"❌ Error fetching item details: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_mock_purchase_orders(self, card_code):
        """Generate mock purchase orders for testing without SAP connectivity"""
        return {

        }
    
    def fetch_po_series(self):
        """
        Fetch PO Series (Document Series) from SAP B1 using SQL Query
        URL: /b1s/v1/SQLQueries('Get_PO_Series')/List
        """
        if not self.ensure_logged_in():
            logging.warning("⚠️ SAP login failed - cannot fetch PO series")
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            url = f"{self.base_url}/b1s/v1/SQLQueries('Get_PO_Series')/List"
            
            logging.info("🔍 Fetching PO Series from SAP")
            response = self.session.post(url, json={}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                series_list = data.get('value', [])
                logging.info(f"✅ Fetched {len(series_list)} PO series")
                return {'success': True, 'series': series_list}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_po_series()
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch PO series: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logging.error(f"❌ Error fetching PO series: {str(e)}")
            return {'success': False, 'error': str(e)}

    def fetch_cardcode_by_series(self, series_id):
        """
        Fetch CardCode by Series ID from SAP B1 Purchase Orders
        Example URL:
        /b1s/v1/PurchaseOrders?$filter=Series eq 987&$select=CardCode,CardName
        """
        if self.enable_mock_data:
            logging.info(f"📋 Using mock cardcode data for series {series_id} (ENABLE_MOCK_SAP_DATA=true)")
            return self.get_mock_cardcodes_by_series(series_id)
        
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - using mock data as fallback for series {series_id}")
            return self.get_mock_cardcodes_by_series(series_id)

        try:
            url = f"{self.base_url}/b1s/v1/PurchaseOrders"
            filter_query = "DocumentStatus eq 'bost_Open'"
            if series_id:
                filter_query = f"Series eq {series_id} and DocumentStatus eq 'bost_Open'"
            
            params = {
                '$filter': filter_query,
                '$select': 'CardCode,CardName,DocumentStatus,DocNum,Series,DocDate,DocDueDate,DocTotal,DocEntry'
            }
            headers = {"Prefer": "odata.maxpagesize=0"}

            logging.info(f"🔍 Fetching CardCodes for series: {series_id} with filter: {filter_query}")
            response = self.session.get(url, params=params, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                all_cardcodes = data.get('value', [])
                
                unique_cardcodes = {}
                for item in all_cardcodes:
                    card_code = item.get('CardCode')
                    if card_code and card_code not in unique_cardcodes:
                        unique_cardcodes[card_code] = item
                
                cardcodes = list(unique_cardcodes.values())
                cardcodes.sort(key=lambda x: x.get('CardName', ''))
                
                logging.info(f"✅ Fetched {len(cardcodes)} unique CardCodes for series {series_id}")
                return {'success': True, 'cardcodes': cardcodes}

            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_cardcode_by_series(series_id)
                logging.warning("⚠️ Authentication failed - using mock data as fallback")
                return self.get_mock_cardcodes_by_series(series_id)

            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch CardCodes for series {series_id}: {error_msg}")
                logging.warning("⚠️ Using mock data as fallback")
                return self.get_mock_cardcodes_by_series(series_id)

        except requests.exceptions.ConnectionError:
            logging.warning(f"⚠️ Cannot connect to SAP server - using mock data as fallback")
            return self.get_mock_cardcodes_by_series(series_id)
        except requests.exceptions.Timeout:
            logging.warning(f"⚠️ SAP request timeout - using mock data as fallback")
            return self.get_mock_cardcodes_by_series(series_id)
        except Exception as e:
            logging.error(f"❌ Error fetching CardCodes for series {series_id}: {str(e)}")
            logging.warning("⚠️ Using mock data as fallback")
            return self.get_mock_cardcodes_by_series(series_id)
    
    def get_bin_abs_entry(self, bin_code):
        """
        Get BinAbsEntry (AbsEntry) for a given bin code
        URL: GET /b1s/v1/BinLocations?$filter=BinCode eq 'BIN_CODE'
        Example: BinCode='7000-FG-A101' returns AbsEntry=251
        """
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - cannot get bin location for {bin_code}")
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            url = f"{self.base_url}/b1s/v1/BinLocations"
            params = {
                '$filter': f"BinCode eq '{bin_code}'",
                '$select': 'AbsEntry,Warehouse,BinCode,Sublevel1,Sublevel2,Sublevel3,Sublevel4'
            }
            
            logging.info(f"🔍 Fetching BinAbsEntry for bin code: {bin_code}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                bins = data.get('value', [])
                
                if not bins:
                    logging.warning(f"⚠️ Bin code {bin_code} not found in SAP")
                    return {'success': False, 'error': f'Bin code {bin_code} not found'}
                
                bin_data = bins[0]
                abs_entry = bin_data.get('AbsEntry')
                warehouse = bin_data.get('Warehouse')
                
                logging.info(f"✅ Found bin {bin_code}: AbsEntry={abs_entry}, Warehouse={warehouse}")
                return {
                    'success': True,
                    'abs_entry': abs_entry,
                    'warehouse': warehouse,
                    'bin_code': bin_code,
                    'bin_data': bin_data
                }
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.get_bin_abs_entry(bin_code)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to get bin location {bin_code}: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logging.error(f"❌ Error getting bin location {bin_code}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def fetch_purchase_orders_by_series_and_card(self, series_id, card_code):
        """
        Fetch open Purchase Orders filtered by Series and CardCode
        Returns only POs with DocumentStatus = 'bost_Open' and open line items
        URL: /b1s/v1/PurchaseOrders?$filter=CardCode eq 'X' and DocumentStatus eq 'bost_Open' and Series eq Y
        """
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - cannot fetch POs for series {series_id} and card {card_code}")
            return {'success': False, 'error': 'SAP login failed'}
        
        try:
            url = f"{self.base_url}/b1s/v1/PurchaseOrders"
            params = {
                '$filter': f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open' and Series eq {series_id}",
                '$select': 'DocEntry,DocNum,CardCode,CardName,DocDate,DocDueDate,DocTotal,DocumentStatus,Series,DocumentLines'
            }
            
            logging.info(f"🔍 Fetching open POs for Series: {series_id}, CardCode: {card_code}")
            logging.info(f"  SAP URL: {url}?$filter={params['$filter']}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                pos = data.get('value', [])
                open_pos = []
                
                for po in pos:
                    document_lines = po.get('DocumentLines', [])
                    open_lines = [
                        line for line in document_lines
                        if line.get('LineStatus') == 'bost_Open' and line.get('Quantity', 0) > 0
                    ]
                    
                    if open_lines:
                        po['OpenLines'] = open_lines
                        po['TotalOpenLines'] = len(open_lines)
                        open_pos.append(po)
                
                logging.info(f"✅ Fetched {len(open_pos)} open POs for series {series_id} and card {card_code}")
                return {'success': True, 'purchase_orders': open_pos}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_purchase_orders_by_series_and_card(series_id, card_code)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch POs: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logging.error(f"❌ Error fetching POs for series {series_id} and card {card_code}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def fetch_customers_from_open_pos(self):
        """
        Fetch unique CardCode/CardName from all open Purchase Orders
        URL: /b1s/v1/PurchaseOrders?$filter=DocumentStatus eq 'bost_Open'&$select=CardCode,CardName
        Returns unique customers who have open POs
        """
        if self.enable_mock_data:
            logging.info("📋 Using mock customer data from open POs (ENABLE_MOCK_SAP_DATA=true)")
            return self.get_mock_customers_from_open_pos()
        
        if not self.ensure_logged_in():
            logging.warning("⚠️ SAP login failed - using mock data as fallback")
            return self.get_mock_customers_from_open_pos()
        
        try:
            url = f"{self.base_url}/b1s/v1/PurchaseOrders"
            params = {
                '$filter': "DocumentStatus eq 'bost_Open'",
                '$select': 'CardCode,CardName'
            }
            headers = {"Prefer": "odata.maxpagesize=0"}
            
            logging.info("🔍 Fetching unique customers from open Purchase Orders")
            response = self.session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                all_customers = data.get('value', [])
                
                unique_customers = {}
                for customer in all_customers:
                    card_code = customer.get('CardCode')
                    card_name = customer.get('CardName')
                    if card_code and card_code not in unique_customers:
                        unique_customers[card_code] = {
                            'CardCode': card_code,
                            'CardName': card_name
                        }
                
                customers_list = list(unique_customers.values())
                customers_list.sort(key=lambda x: x.get('CardName', ''))
                
                logging.info(f"✅ Fetched {len(customers_list)} unique customers from open POs")
                return {'success': True, 'customers': customers_list}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_customers_from_open_pos()
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch customers from open POs: {error_msg}")
                logging.warning("⚠️ Using mock data as fallback")
                return self.get_mock_customers_from_open_pos()
                
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"⚠️ Cannot connect to SAP server - using mock data as fallback")
            return self.get_mock_customers_from_open_pos()
        except requests.exceptions.Timeout:
            logging.warning(f"⚠️ SAP request timeout - using mock data as fallback")
            return self.get_mock_customers_from_open_pos()
        except Exception as e:
            logging.error(f"❌ Error fetching customers from open POs: {str(e)}")
            logging.warning("⚠️ Using mock data as fallback")
            return self.get_mock_customers_from_open_pos()

    def get_mock_purchase_orders(self, card_code):
        """Generate mock purchase orders for testing without SAP connectivity"""
        from datetime import datetime, timedelta
        today = datetime.now()
        return {
            'success': True,
            'purchase_orders': [
                {
                    'DocEntry': 1001,
                    'DocNum': 'PO-1001',
                    'CardCode': card_code,
                    'CardName': 'Mock Customer',
                    'DocDate': today.strftime('%Y-%m-%d'),
                    'DocDueDate': (today + timedelta(days=30)).strftime('%Y-%m-%d'),
                    'DocTotal': 15000.00,
                    'Series': 1
                },
                {
                    'DocEntry': 1002,
                    'DocNum': 'PO-1002',
                    'CardCode': card_code,
                    'CardName': 'Mock Customer',
                    'DocDate': today.strftime('%Y-%m-%d'),
                    'DocDueDate': (today + timedelta(days=45)).strftime('%Y-%m-%d'),
                    'DocTotal': 25000.00,
                    'Series': 1
                },
                {
                    'DocEntry': 1003,
                    'DocNum': 'PO-1003',
                    'CardCode': card_code,
                    'CardName': 'Mock Customer',
                    'DocDate': (today - timedelta(days=5)).strftime('%Y-%m-%d'),
                    'DocDueDate': (today + timedelta(days=25)).strftime('%Y-%m-%d'),
                    'DocTotal': 8500.00,
                    'Series': 1
                }
            ]
        }

    def fetch_pos_by_cardcode(self, card_code):
        """
        Fetch open Purchase Orders filtered by CardCode only
        URL: /b1s/v1/PurchaseOrders?$select=CardCode,CardName,DocumentStatus,DocNum,Series,DocDate,DocDueDate,DocTotal,DocEntry&$filter=CardCode eq 'XXX' and DocumentStatus eq 'bost_Open'
        Returns POs with all details needed for selection screen
        """
        if self.enable_mock_data:
            logging.info(f"📋 Using mock PO data for CardCode {card_code} (ENABLE_MOCK_SAP_DATA=true)")
            return self.get_mock_purchase_orders(card_code)
        
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - using mock data as fallback")
            return self.get_mock_purchase_orders(card_code)
        
        try:
            url = f"{self.base_url}/b1s/v1/PurchaseOrders"
            params = {
                '$filter': f"CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'",
                '$select': 'CardCode,CardName,DocumentStatus,DocNum,Series,DocDate,DocDueDate,DocTotal,DocEntry'
            }
            headers = {"Prefer": "odata.maxpagesize=0"}
            
            logging.info(f"🔍 Fetching open POs for CardCode: {card_code}")
            response = self.session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                pos = data.get('value', [])
                logging.info(f"✅ Fetched {len(pos)} open POs for CardCode {card_code}")
                return {'success': True, 'purchase_orders': pos}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_pos_by_cardcode(card_code)
                return {'success': False, 'error': 'Authentication failed'}
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch POs for CardCode {card_code}: {error_msg}")
                logging.warning("⚠️ Using mock data as fallback")
                return self.get_mock_purchase_orders(card_code)
                
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"⚠️ Cannot connect to SAP server - using mock data as fallback")
            return self.get_mock_purchase_orders(card_code)
        except requests.exceptions.Timeout:
            logging.warning(f"⚠️ SAP request timeout - using mock data as fallback")
            return self.get_mock_purchase_orders(card_code)
        except Exception as e:
            logging.error(f"❌ Error fetching POs for CardCode {card_code}: {str(e)}")
            logging.warning("⚠️ Using mock data as fallback")
            return self.get_mock_purchase_orders(card_code)

    def fetch_po_lines_by_docentry(self, doc_entry):
        """
        Fetch Purchase Order details including line items by DocEntry using $crossjoin
        URL: /b1s/v1/$crossjoin(PurchaseOrders,PurchaseOrders/DocumentLines)?$expand=...&$filter=...DocEntry eq X
        Returns full PO details with DocumentLines in the $crossjoin response format
        """
        if self.enable_mock_data:
            logging.info(f"📋 Using mock PO lines for DocEntry {doc_entry} (ENABLE_MOCK_SAP_DATA=true)")
            return self.get_mock_po_lines(doc_entry)
        
        if not self.ensure_logged_in():
            logging.warning(f"⚠️ SAP login failed - using mock data as fallback for DocEntry {doc_entry}")
            return self.get_mock_po_lines(doc_entry)
        
        try:
            url = (
                f"{self.base_url}/b1s/v1/$crossjoin(PurchaseOrders,PurchaseOrders/DocumentLines)"
                f"?$expand=PurchaseOrders($select=CardCode,CardName,DocumentStatus,DocNum,Series,DocDate,DocDueDate,DocTotal,DocEntry),"
                f"PurchaseOrders/DocumentLines($select=LineNum,ItemCode,ItemDescription,WarehouseCode,UnitsOfMeasurment,DocEntry,LineTotal,LineStatus,Quantity,Price,PriceAfterVAT)"
                f"&$filter=PurchaseOrders/DocumentStatus eq PurchaseOrders/DocumentLines/LineStatus "
                f"and PurchaseOrders/DocEntry eq PurchaseOrders/DocumentLines/DocEntry "
                f"and PurchaseOrders/DocumentLines/DocEntry eq {doc_entry}"
            )
            
            logging.info(f"🔍 Fetching PO lines using $crossjoin for DocEntry: {doc_entry}")
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                crossjoin_values = data.get('value', [])
                
                if not crossjoin_values:
                    logging.warning(f"⚠️ No data found for DocEntry {doc_entry}")
                    return {'success': False, 'error': f'No data found for DocEntry {doc_entry}'}
                
                first_record = crossjoin_values[0]
                po_header = first_record.get('PurchaseOrders', {})
                
                document_lines = []
                open_lines = []
                for record in crossjoin_values:
                    line_data = record.get('PurchaseOrders/DocumentLines', {})
                    if line_data:
                        document_lines.append(line_data)
                        if line_data.get('LineStatus') == 'O' and line_data.get('Quantity', 0) > 0:
                            open_lines.append(line_data)
                
                po_data = {
                    **po_header,
                    'DocumentLines': document_lines,
                    'OpenLines': open_lines,
                    'TotalOpenLines': len(open_lines)
                }
                
                logging.info(f"✅ Fetched PO {doc_entry} with {len(open_lines)} open lines using $crossjoin")
                return {'success': True, 'purchase_order': po_data}
            elif response.status_code == 401:
                self.session_id = None
                if self.login():
                    return self.fetch_po_lines_by_docentry(doc_entry)
                logging.warning("⚠️ Authentication failed - using mock data as fallback")
                return self.get_mock_po_lines(doc_entry)
            elif response.status_code == 404:
                logging.warning(f"⚠️ DocEntry {doc_entry} not found - using mock data as fallback")
                return self.get_mock_po_lines(doc_entry)
            else:
                error_msg = response.text
                logging.error(f"❌ Failed to fetch PO lines for DocEntry {doc_entry}: {error_msg}")
                logging.warning("⚠️ Using mock data as fallback")
                return self.get_mock_po_lines(doc_entry)
                
        except requests.exceptions.ConnectionError:
            logging.warning(f"⚠️ Cannot connect to SAP server - using mock data as fallback")
            return self.get_mock_po_lines(doc_entry)
        except requests.exceptions.Timeout:
            logging.warning(f"⚠️ SAP request timeout - using mock data as fallback")
            return self.get_mock_po_lines(doc_entry)
        except Exception as e:
            logging.error(f"❌ Error fetching PO lines for DocEntry {doc_entry}: {str(e)}")
            logging.warning("⚠️ Using mock data as fallback")
            return self.get_mock_po_lines(doc_entry)
