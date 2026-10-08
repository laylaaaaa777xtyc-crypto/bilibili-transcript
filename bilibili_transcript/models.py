"""Source and processed transcript models used by post-processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Transcript:
    """Immutable-by-convention view of the raw transcript fact source."""

    video_id: str
    title: str
    segments: List[Dict[str, Any]]
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transcript":
        return cls(
            video_id=str(data.get("video_id") or data.get("bvid") or ""),
            title=str(data.get("title") or data.get("video_id") or "Untitled"),
            segments=list(data.get("segments") or []),
            text=str(data.get("text") or ""),
            metadata=dict(data),
        )


@dataclass
class ProcessedTranscript:
    """Readable text derived from a raw :class:`Transcript`."""

    title: str
    paragraphs: List[str]

    @property
    def text(self) -> str:
        return "\n\n".join(p for p in self.paragraphs if p).strip()
