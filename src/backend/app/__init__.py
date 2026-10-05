"""Backend bootstrap: fixed sibling src path for the shared internal core."""
from pathlib import Path
import sys
_SOURCE_ROOT=str(Path(__file__).resolve().parents[2])
if _SOURCE_ROOT not in sys.path:sys.path.insert(0,_SOURCE_ROOT)
