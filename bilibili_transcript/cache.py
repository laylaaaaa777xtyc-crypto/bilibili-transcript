"""Transcript cache discovery and loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def find_cached_transcript(out_dir: Path, video_id: str) -> Optional[Path]:
    for candidate in (
        out_dir / "transcript.json",
        out_dir / f"{video_id}_transcript.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_cached_transcript(out_dir: Path, video_id: str) -> Optional[Dict[str, Any]]:
    path = find_cached_transcript(out_dir, video_id)
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("segments"):
        return None
    return data
