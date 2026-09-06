import json
from pathlib import Path
from datetime import datetime, timezone
import os

class RawStore:
    def __init__(self, root=None):
        self.root = Path(root or os.getenv("DATA_DIR", "./data"))
        self.root.mkdir(parents=True, exist_ok=True)

    def save_json(self, payload, relative_path):
        path = self.root / "raw" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return path

    def save_bytes(self, content, relative_path):
        path = self.root / "raw" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def save_raw_file(self, src_path, relative_path):
        path = self.root / "raw" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(src_path, path)
        return path

    def read_csv(self, relative_path):
        import pandas as pd
        path = self.root / "raw" / relative_path
        return pd.read_csv(path)
