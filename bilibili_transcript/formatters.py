"""Plain-text, article, and SRT formatters for transcript data."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from bilibili_transcript.models import ProcessedTranscript


def format_txt(processed: ProcessedTranscript) -> str:
    return processed.text + ("\n" if processed.text else "")


def format_article_markdown(processed: ProcessedTranscript) -> str:
    body = processed.text
    return f"# {processed.title}\n\n{body}\n" if body else f"# {processed.title}\n"


def _srt_timestamp(seconds: float) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_srt(segments: Iterable[Dict[str, Any]]) -> str:
    blocks = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start") or 0.0)
        end = max(start, float(segment.get("end") or start))
        index = len(blocks) + 1
        blocks.append(
            f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
