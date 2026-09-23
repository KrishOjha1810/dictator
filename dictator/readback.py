"""Read the text field the user is editing, so corrections can be noticed.

Dictation pastes words and then never looks again, which means the most useful
signal it could possibly have is thrown away every time: if you fixed
"whisper floor" to "Whisper Flow" by hand, that is you telling it the right
answer, in the one moment you actually know it.

This module only reads. It never writes into the field, and it never stores
what it read: the caller compares it against what was pasted and keeps the
difference, not the document.
"""
import json
import shutil
import subprocess
from pathlib import Path

from . import core

SRC = Path(__file__).resolve().parent.parent / "native" / "readback.swift"
BIN = core.STATE_DIR / "bin" / "dictator-readback"


def build(force: bool = False) -> str:
    """Compile the reader if needed. Returns a path, or "" with a reason
    logged. Rebuilds when the source is newer than the binary."""
    if not SRC.exists():
        core.log(f"readback: source missing at {SRC}")
        return ""
    if BIN.exists() and not force and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return str(BIN)
    if not shutil.which("swiftc"):
        core.log("readback: swiftc not found")
        return ""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", str(SRC), "-o", str(BIN)],
                       check=True, capture_output=True, timeout=180)
        return str(BIN)
    except subprocess.CalledProcessError as e:
        core.log(f"readback: build failed: {e.stderr.decode()[:400]}")
    except Exception as e:
        core.log(f"readback: build failed: {e}")
    return ""


def field() -> dict:
    """What is in the focused text field right now.

    Returns {"ok": bool, "app": str, "role": str, "value": str|None,
    "selected": str}. Never raises: this runs on the dictation path and a
    failure to read somebody's text field must never be the reason the key
    stops working."""
    try:
        exe = build()
        if not exe:
            return {"ok": False, "why": "reader not built"}
        r = subprocess.run([exe], capture_output=True, text=True, timeout=5)
        if not r.stdout.strip():
            return {"ok": False, "why": (r.stderr or "no output").strip()[:200]}
        return json.loads(r.stdout)
    except Exception as e:
        return {"ok": False, "why": str(e)[:200]}
