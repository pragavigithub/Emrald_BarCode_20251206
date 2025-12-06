"""
SO Against Invoice Module

This module handles creating invoices against Sales Orders with validation.
Includes SAP B1 integration for fetching SO details and posting invoices.
"""

from .routes import so_invoice_bp

__all__ = ['so_invoice_bp']