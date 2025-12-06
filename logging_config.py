import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging(app):
    """
    Configure comprehensive logging for the WMS application
    Logs will be written to C:\\tmp\\wms_logs on Windows or /tmp/wms_logs on Linux
    """
    
    # Determine log directory based on OS
    if os.name == 'nt':  # Windows
        log_dir = r'C:\tmp\wms_logs'
    else:  # Linux/Unix (Replit)
        log_dir = '/tmp/wms_logs'
    
    # Create log directory if it doesn't exist
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create log directory {log_dir}: {e}")
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
    
    # Define log file paths
    main_log_file = os.path.join(log_dir, 'wms_application.log')
    error_log_file = os.path.join(log_dir, 'wms_errors.log')
    sap_log_file = os.path.join(log_dir, 'sap_integration.log')
    database_log_file = os.path.join(log_dir, 'database_operations.log')
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s (%(funcName)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Main application log handler (INFO and above, max 10MB, keep 5 backups)
    main_handler = RotatingFileHandler(
        main_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(detailed_formatter)
    
    # Error log handler (ERROR and above, max 10MB, keep 10 backups)
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # SAP integration log handler
    sap_handler = RotatingFileHandler(
        sap_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    sap_handler.setLevel(logging.DEBUG)
    sap_handler.setFormatter(detailed_formatter)
    
    # Database operations log handler
    db_handler = RotatingFileHandler(
        database_log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    db_handler.setLevel(logging.DEBUG)
    db_handler.setFormatter(detailed_formatter)
    
    # Configure Flask app logger
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(main_handler)
    app.logger.addHandler(error_handler)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(main_handler)
    root_logger.addHandler(error_handler)
    
    # Configure SAP integration logger
    sap_logger = logging.getLogger('sap_integration')
    sap_logger.setLevel(logging.DEBUG)
    sap_logger.addHandler(sap_handler)
    sap_logger.addHandler(error_handler)
    
    # Configure database logger
    db_logger = logging.getLogger('sqlalchemy')
    db_logger.setLevel(logging.WARNING)  # Only log warnings and errors from SQLAlchemy
    db_logger.addHandler(db_handler)
    
    # Configure werkzeug logger (Flask's HTTP server)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(main_handler)
    
    # Log startup message
    app.logger.info("="*80)
    app.logger.info(f"WMS Application Started - Log Directory: {log_dir}")
    app.logger.info(f"Main Log: {main_log_file}")
    app.logger.info(f"Error Log: {error_log_file}")
    app.logger.info(f"SAP Log: {sap_log_file}")
    app.logger.info(f"Database Log: {database_log_file}")
    app.logger.info("="*80)
    
    return log_dir
