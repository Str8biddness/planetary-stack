import sys
import os
from pathlib import Path

# Add root to sys.path
PROJ_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ_ROOT))

try:
    from cognitive.cognitive_engine import CognitiveEngine
    print("CognitiveEngine imported successfully")
    
    # Try minimal instantiation
    engine = CognitiveEngine(character_id="synth")
    print("CognitiveEngine instantiated successfully")
except Exception as e:
    import traceback
    traceback.print_exc()
