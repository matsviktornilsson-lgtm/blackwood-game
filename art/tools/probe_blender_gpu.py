"""Enumerate Cycles devices in an isolated Blender process."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_model import configure_cycles

print("BLACKWOOD_GPU_REPORT=" + json.dumps({"device": configure_cycles()}), flush=True)
