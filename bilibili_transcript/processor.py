"""Readable transcript processing, deliberately separate from subtitle/ASR."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Protocol

from bilibili_transcript.models import ProcessedTranscript, Transcript

_SENTENCE_END = re.compile(r"[。！？!?；;…][\"'”’）】》]?$|\.(?:[\"']?)$")
_CJK = r"\u3400-\u9fff"


def clean_text(text: str) -> str:
    """Normalize whitespace and obvious punctuation without rewriting words."""
    value = re.sub(r"[\t\r\f\v]+", " ", str(text or ""))
    value = re.sub(r"\s*\n\s*", " ", value)
    value = re.sub(r" {2,}", " ", value).strip()
    # Spaces between CJK characters or next to Chinese punctuation are artifacts.
    value = re.sub(rf"(?<=[{_CJK}]) +(?=[{_CJK}])", "", value)
    value = re.sub(r"\s+([，。！？；：、])", r"\1", value)
    value = re.sub(r"([（【《])\s+", r"\1", value)
    value = re.sub(r"([，。！？；：、])\1+", r"\1", value)
    value = re.sub(r"([!?]){2,}", r"\1", value)
    return value


def _join_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if re.search(rf"[{_CJK}，。！？；：、（【《]$", left) or re.match(
        rf"^[{_CJK}，。！？；：、）】》]", right
    ):
        return left + right
    return left + " " + right


class TranscriptProcessor(ABC):
    @abstractmethod
    def process(self, transcript: Transcript) -> ProcessedTranscript:
        """Return readable derived text while leaving the raw transcript intact."""


class RuleBasedProcessor(TranscriptProcessor):
    """Conservative, deterministic cleanup and paragraphing."""

    def __init__(self, min_paragraph_chars: int = 80, max_paragraph_chars: int = 260):
        self.min_paragraph_chars = min_paragraph_chars
        self.max_paragraph_chars = max_paragraph_chars

    def process(self, transcript: Transcript) -> ProcessedTranscript:
        paragraphs: List[str] = []
        current = ""
        previous = ""
        previous_end = 0.0
        previous_part = None

        for segment in transcript.segments:
            text = clean_text(segment.get("text") or "")
            normalized = re.sub(r"\s+", "", text)
            if not normalized or normalized == previous:
                continue

            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or start)
            part = segment.get("part")
            boundary = bool(
                current
                and (
                    (previous_part is not None and part != previous_part)
                    or start - previous_end >= 2.5
                    or len(current) >= self.max_paragraph_chars
                    or (
                        len(current) >= self.min_paragraph_chars
                        and _SENTENCE_END.search(current)
                    )
                )
            )
            if boundary:
                paragraphs.append(current.strip())
                current = ""
            current = _join_text(current, text)
            previous = normalized
            previous_end = end
            previous_part = part

        if current:
            paragraphs.append(current.strip())

        return ProcessedTranscript(title=transcript.title, paragraphs=paragraphs)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class LLMProcessor(TranscriptProcessor):
    """Provider-neutral LLM adapter reserved for optional future integrations."""

    def __init__(self, client: LLMClient):
        self.client = client

    def process(self, transcript: Transcript) -> ProcessedTranscript:
        source = RuleBasedProcessor().process(transcript).text
        prompt = (
            "请在不改变事实、不增删信息的前提下，将以下视频转写整理为自然段文稿。"
            "只返回正文。\n\n" + source
        )
        result = self.client.complete(prompt).strip()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", result) if p.strip()]
        return ProcessedTranscript(title=transcript.title, paragraphs=paragraphs)


class MockLLMClient:
    """Small deterministic client for tests and downstream integration examples."""

    def __init__(self, response: str):
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response
