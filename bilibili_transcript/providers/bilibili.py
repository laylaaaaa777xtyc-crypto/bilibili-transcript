"""Bilibili provider — wraps existing bilibili-specific modules."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from bilibili_transcript.bvid import BV_RE, extract_bvid, video_page_url_part
from bilibili_transcript.download import download_part_mp3, fetch_pagelist
from bilibili_transcript.meta import fetch_video_meta
from bilibili_transcript.providers.base import (
    Segments,
    SourceRecord,
    TranscriptProvider,
    VideoMeta,
)
from bilibili_transcript.subtitles import (
    try_fetch_official_segments,
    try_fetch_subtitles_ytdlp,
)
from bilibili_transcript.validation import BasicSubtitleValidator

logger = logging.getLogger(__name__)


class BilibiliProvider(TranscriptProvider):
    name = "bilibili"

    def match(self, url_or_id: str) -> bool:
        s = url_or_id.strip()
        return bool(BV_RE.search(s)) or "bilibili.com" in s or "b23.tv" in s

    def extract_id(self, url_or_id: str) -> str:
        return extract_bvid(url_or_id)

    def fetch_metadata(self, video_id: str, **kwargs: Any) -> VideoMeta:
        meta = fetch_video_meta(video_id)
        pages = meta.get("pages") or []
        if not pages:
            pages = fetch_pagelist(video_id)
        title = meta.get("title") or video_id
        aid = int(meta.get("aid") or 0)
        return VideoMeta(
            video_id=video_id,
            title=title,
            aid=aid,
            pages=pages,
            extra=meta,
        )

    def fetch_segments(
        self,
        meta: VideoMeta,
        part_index: int,
        cid: int,
        *,
        args: argparse.Namespace,
    ) -> Optional[Tuple[Segments, str, SourceRecord]]:
        if getattr(args, "force_asr", False) or not getattr(args, "prefer_subtitles", True):
            return None

        page_url = video_page_url_part(meta.video_id, part_index)
        duration = 0.0
        if 0 < part_index <= len(meta.pages):
            duration = float(meta.pages[part_index - 1].get("duration") or 0.0)
        validator = BasicSubtitleValidator()

        cookies_from_browser = getattr(args, "cookies_from_browser", None)
        off = None
        if meta.aid:
            try:
                off = try_fetch_official_segments(
                    meta.video_id,
                    cid,
                    meta.aid,
                    cookies_from_browser=cookies_from_browser,
                )
            except Exception as exc:
                logger.warning("官方字幕获取失败：%s，将继续 fallback。", exc)
        else:
            logger.warning("元数据中缺少 aid，跳过官方字幕并继续 fallback。")
        if off:
            segs, full, track_meta = off
            validation = validator.validate(segs, duration)
            if validation.valid:
                return segs, full, SourceRecord(
                    part=part_index,
                    mode="official_cc",
                    extra={
                        "lan": track_meta.get("lan"),
                        "subtitle_url": track_meta.get("subtitle_url"),
                        "validation": validation.to_dict(),
                    },
                )
            logger.warning("官方字幕可靠性检测未通过：%s，将继续 fallback。", validation.reason)

        if cookies_from_browser or getattr(args, "ytdlp_subs", False):
            yd = try_fetch_subtitles_ytdlp(
                page_url, cookies_from_browser=cookies_from_browser,
            )
            if yd:
                segs, full = yd
                validation = validator.validate(segs, duration)
                if validation.valid:
                    return segs, full, SourceRecord(
                        part=part_index,
                        mode="ytdlp_subtitle_file",
                        extra={"validation": validation.to_dict()},
                    )
                logger.warning("yt-dlp 字幕可靠性检测未通过：%s，将回退 ASR。", validation.reason)

        return None

    def download_audio(
        self,
        meta: VideoMeta,
        part_index: int,
        cid: int,
        out_dir: Path,
        *,
        args: argparse.Namespace,
    ) -> Path:
        return download_part_mp3(
            meta.video_id,
            page=part_index,
            cid=cid,
            out_dir=out_dir,
            prefer_ytdlp=getattr(args, "ytdlp", False),
            cookies_from_browser=getattr(args, "cookies_from_browser", None),
        )
