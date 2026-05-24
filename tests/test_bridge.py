import sys
import os
from pathlib import Path

# Add build directory to path for the pybind module
sys.path.insert(0, str(Path("build").resolve()))

# Import the bridge
from kernel.hardware_cloud_bridge import create_bridged_emul_engine

def test_lookup():
    print("--- Hardware-to-Cloud Bridge Test ---")
    
    # Paths are relative to the script execution or project root
    try:
        engine = create_bridged_emul_engine(
            top_k=3,
            index_path="data/knowledge_cache/faiss.index",
            metadata_path="data/knowledge_cache/faiss_metadata.json",
            model_dir="data/knowledge_cache/models"
        )
        
        print("\nEngine Initialized.")
        
        # Test lookups
        queries = ["intel_npu_v1", "ddr5_ram", "AVX-512"]
        
        for q in queries:
            print(f"\nQuerying: {q}")
            result_json = engine.query_blueprints(q)
            print(f"Result: {result_json}")
            
        print("\nTest Complete.")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_lookup()
