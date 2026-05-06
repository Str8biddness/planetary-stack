# Synthesus 2.0 - modules package
from .python_fallback import PythonFallback
from .web_scraper import scrape, fetch_page, extract_text
from .vehicle_py import lookup_dtc, sensor_fusion, plan_route

__all__ = [
    "PythonFallback",
    "scrape", "fetch_page", "extract_text",
    "lookup_dtc", "sensor_fusion", "plan_route",
]