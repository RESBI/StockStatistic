"""Admin plugin — web management interface for StockStat storage backend.

Usage:
    from stockstat_backend.plugins.admin import AdminPlugin
    AdminPlugin.mount(app)
"""
from .plugin import AdminPlugin

__all__ = ["AdminPlugin"]
