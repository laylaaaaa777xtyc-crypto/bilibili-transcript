"""Bilibili video metadata (title, etc.)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

from bilibili_transcript.bvid import video_page_url
from bilibili_transcript.download import DEFAULT_UA

logger = logging.getLogger(__name__)

VIEW_URL = "https://api.bilibili.com/x/web-interface/view"


def _headers(bvid: str) -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_UA,
        "Referer": video_page_url(bvid),
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }


def fetch_video_meta_from_page(bvid: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Read ``videoData`` embedded in the public video page.

    Bilibili occasionally rejects the JSON view endpoint with HTTP 412 while
    the public video page remains available. The page carries the same core
    metadata in ``window.__INITIAL_STATE__`` and is therefore a safe fallback.
    """
    response = requests.get(
        video_page_url(bvid),
        headers=_headers(bvid),
        timeout=timeout,
    )
    response.raise_for_status()
    marker = "window.__INITIAL_STATE__="
    position = response.text.find(marker)
    if position < 0:
        raise RuntimeError("video page does not contain __INITIAL_STATE__")
    payload = response.text[position + len(marker):]
    state, _end = json.JSONDecoder().raw_decode(payload)
    video_data = state.get("videoData") or {}
    if not video_data or video_data.get("bvid") != bvid:
        raise RuntimeError("video page did not contain matching videoData")
    return video_data


def fetch_video_meta(bvid: str, timeout: float = 30.0) -> Dict[str, Any]:
    try:
        response = requests.get(
            VIEW_URL,
            params={"bvid": bvid},
            headers=_headers(bvid),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"view API failed: {payload}")
        data = payload.get("data") or {}
        if data:
            return data
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        logger.warning("Bilibili view API unavailable (%s); using video page metadata.", exc)
    return fetch_video_meta_from_page(bvid, timeout=timeout)


def video_title(bvid: str) -> Optional[str]:
    try:
        data = fetch_video_meta(bvid)
        return data.get("title")
    except Exception as e:
        logger.warning("Could not fetch video title: %s", e)
        return None
