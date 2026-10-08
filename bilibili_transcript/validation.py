"""Conservative subtitle reliability checks before accepting a subtitle track."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Sequence


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    confidence: float
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class SubtitleValidator(ABC):
    @abstractmethod
    def validate(
        self,
        segments: Sequence[Dict[str, Any]],
        video_duration: float = 0.0,
    ) -> ValidationResult:
        ...


class BasicSubtitleValidator(SubtitleValidator):
    def validate(
        self,
        segments: Sequence[Dict[str, Any]],
        video_duration: float = 0.0,
    ) -> ValidationResult:
        if not segments:
            return ValidationResult(False, 0.0, "字幕为空")

        texts = [str(s.get("text") or "").strip() for s in segments]
        texts = [t for t in texts if t]
        total_chars = sum(len(re.sub(r"\s+", "", t)) for t in texts)
        if not texts or total_chars < 10:
            return ValidationResult(False, 0.05, "字幕长度异常：有效文字过少")
        if total_chars / len(texts) > 500:
            return ValidationResult(False, 0.2, "字幕长度异常：单条字幕过长")

        timestamp_errors = 0
        previous_start = -1.0
        for segment in segments:
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or 0.0)
            if start < 0 or end < start or start + 0.01 < previous_start:
                timestamp_errors += 1
            previous_start = start
        if timestamp_errors / len(segments) > 0.05:
            return ValidationResult(False, 0.1, "时间戳异常")

        normalized = [re.sub(r"[\W_]+", "", t).lower() for t in texts]
        counts = Counter(t for t in normalized if t)
        duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
        duplicate_ratio = duplicate_count / max(1, len(normalized))
        if len(normalized) >= 5 and duplicate_ratio >= 0.6:
            return ValidationResult(False, 0.15, "大量重复句")

        if video_duration >= 600 and total_chars < max(80, video_duration * 0.12):
            return ValidationResult(False, 0.2, "视频很长但字幕字数极少")

        confidence = max(0.5, 0.98 - duplicate_ratio * 0.5 - timestamp_errors * 0.03)
        return ValidationResult(True, round(confidence, 2), "")
