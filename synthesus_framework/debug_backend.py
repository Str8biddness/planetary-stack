import sys
import os
import traceback

# Add current dir to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from api.production_server import app
    print("Backend imported successfully!")
except Exception:
    traceback.print_exc()
