#!/usr/bin/env python3
"""Utility for computing stable file hashes used as track IDs."""

from pathlib import Path
import hashlib


def compute_file_hash(path: Path, algo: str = "sha256") -> str:
    """Compute a hash of a file in streaming mode (1 MB chunks).

    This is used as a stable identifier for a given audio file across all
    pipeline segments (match / analyse / merge / load).
    """
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
