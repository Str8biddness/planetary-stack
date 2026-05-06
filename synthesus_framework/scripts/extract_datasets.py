import os
import zipfile
from pathlib import Path

datasets_dir = Path("datasets")
extracted_dir = datasets_dir / "extracted"
extracted_dir.mkdir(exist_ok=True)

for zf in datasets_dir.glob("*.zip"):
    print(f"Extracting {zf.name}...")
    try:
        with zipfile.ZipFile(zf, 'r') as zip_ref:
            zip_ref.extractall(extracted_dir)
    except Exception as e:
        print(f"Failed to extract {zf.name}: {e}")

print("Extraction complete.")
