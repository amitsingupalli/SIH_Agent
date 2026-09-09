"""Model Context Protocol (FastMCP) server and healthcare tools."""
from .server import (
    mcp_server,
    log_vitals,
    check_hospital_capacity,
    book_referral,
    send_vernacular_alert,
    check_stock_runway,
    REFERRAL_STORE,
    PATIENT_RECORDS,
    PHC_INVENTORY_STORE
)

__all__ = [
    "mcp_server",
    "log_vitals",
    "check_hospital_capacity",
    "book_referral",
    "send_vernacular_alert",
    "check_stock_runway",
    "REFERRAL_STORE",
    "PATIENT_RECORDS",
    "PHC_INVENTORY_STORE",
]
