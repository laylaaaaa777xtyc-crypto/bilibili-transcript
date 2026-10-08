"""Download Bilibili audio via pagelist + playurl, transcode to MP3; yt-dlp fallback."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from bilibili_transcript.bvid import video_page_url

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PAGELIST_URL = "https://api.bilibili.com/x/player/pagelist"
PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"
_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)


def _session_headers(bvid: str) -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_UA,
        "Referer": video_page_url(bvid),
        "Origin": "https://www.bilibili.com",
    }


def fetch_pagelist(bvid: str, timeout: float = 30.0) -> List[Dict[str, Any]]:
    r = requests.get(
        PAGELIST_URL,
        params={"bvid": bvid},
        headers=_session_headers(bvid),
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"pagelist error: {data}")
    pages = data.get("data") or []
    if not pages:
        raise RuntimeError("pagelist returned no pages")
    return pages


def _pick_audio_urls(playurl_json: Dict[str, Any]) -> List[str]:
    d = playurl_json.get("data") or {}
    dash = d.get("dash")
    if not dash:
        return []
    audios = dash.get("audio") or []
    if not audios:
        return []
    # Prefer highest bandwidth
    audios = sorted(audios, key=lambda x: int(x.get("bandwidth") or 0), reverse=True)
    selected = audios[0]
    urls: List[str] = []
    base = selected.get("baseUrl") or selected.get("base_url")
    if base:
        urls.append(base)
    backups = selected.get("backupUrl") or selected.get("backup_url") or []
    urls.extend(url for url in backups if url and url not in urls)
    return urls


def _pick_audio_url(playurl_json: Dict[str, Any]) -> Optional[str]:
    """Backward-compatible single URL selector."""
    urls = _pick_audio_urls(playurl_json)
    return urls[0] if urls else None


def fetch_playurl(
    bvid: str,
    cid: int,
    timeout: float = 30.0,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return (raw_json, audio_url_or_none). Tries fnval values for DASH."""
    fnvals = (4048, 16, 80)
    last: Optional[Dict[str, Any]] = None
    for fnval in fnvals:
        r = requests.get(
            PLAYURL_URL,
            params={
                "bvid": bvid,
                "cid": cid,
                "qn": 80,
                "fnval": fnval,
                "fourk": 1,
            },
            headers=_session_headers(bvid),
            timeout=timeout,
        )
        r.raise_for_status()
        j = r.json()
        last = j
        if j.get("code") != 0:
            logger.warning("playurl code=%s message=%s fnval=%s", j.get("code"), j.get("message"), fnval)
            continue
        url = _pick_audio_url(j)
        if url:
            return j, url
    return last or {}, None


def download_url_to_file(
    url: str,
    dest: Path,
    bvid: str,
    timeout: float = 600.0,
    max_attempts: int = 6,
    chunk_bytes: int = 8 * 1024 * 1024,
) -> None:
    """Download large media in validated HTTP Range chunks.

    A chunk is kept in memory and appended only after its Content-Range and
    byte count are verified. A broken connection therefore cannot corrupt the
    completed prefix on disk.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe_headers = _session_headers(bvid)
    probe_headers["Range"] = "bytes=0-0"
    with requests.get(url, headers=probe_headers, stream=True, timeout=timeout) as probe:
        probe.raise_for_status()
        match = _CONTENT_RANGE.fullmatch(probe.headers.get("Content-Range", "").strip())
        if probe.status_code != 206 or not match:
            raise RuntimeError("audio CDN does not support validated byte ranges")
        total_size = int(match.group(3))

    offset = dest.stat().st_size if dest.exists() else 0
    if offset > total_size:
        with open(dest, "wb"):
            pass
        offset = 0
    if offset == total_size:
        return
    if offset:
        logger.info("Resuming validated audio download at %.1f MB…", offset / 1024 / 1024)

    while offset < total_size:
        end = min(offset + chunk_bytes - 1, total_size - 1)
        expected_length = end - offset + 1
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            headers = _session_headers(bvid)
            headers["Range"] = f"bytes={offset}-{end}"
            try:
                with requests.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    content_range = _CONTENT_RANGE.fullmatch(
                        response.headers.get("Content-Range", "").strip()
                    )
                    if response.status_code != 206 or not content_range:
                        raise IOError("audio CDN returned an unvalidated range response")
                    actual_start, actual_end, actual_total = map(int, content_range.groups())
                    if (actual_start, actual_end, actual_total) != (offset, end, total_size):
                        raise IOError(
                            "audio CDN returned wrong range "
                            f"{actual_start}-{actual_end}/{actual_total}; "
                            f"expected {offset}-{end}/{total_size}"
                        )
                    buffer = bytearray()
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            buffer.extend(chunk)
                if len(buffer) != expected_length:
                    raise IOError(
                        f"incomplete audio chunk: {len(buffer)}/{expected_length} bytes"
                    )
                with open(dest, "ab") as file_handle:
                    file_handle.write(buffer)
                offset = end + 1
                break
            except (requests.RequestException, OSError) as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                logger.warning(
                    "Audio chunk %.1f-%.1f MB interrupted (%s); retrying %s/%s…",
                    offset / 1024 / 1024,
                    (end + 1) / 1024 / 1024,
                    exc,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(min(2 ** (attempt - 1), 4))
        else:
            continue
        if offset <= end:
            raise RuntimeError(
                f"audio chunk download failed after {max_attempts} attempts: {last_error}"
            )


def transcode_to_mp3(src: Path, dst: Path, bitrate: str = "192k") -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-acodec",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def download_audio_via_api(
    bvid: str,
    cid: int,
    work_dir: Path,
    basename: str,
    bitrate: str = "192k",
) -> Path:
    playurl_json, audio_url = fetch_playurl(bvid, cid)
    if not audio_url:
        raise RuntimeError("playurl did not return DASH audio URL")

    suffix = _guess_suffix(audio_url)
    raw_path = work_dir / f"{basename}_raw{suffix}"
    mp3_path = work_dir / f"{basename}.mp3"

    logger.info("Downloading audio from DASH…")
    download_errors: List[str] = []
    for candidate_url in _pick_audio_urls(playurl_json) or [audio_url]:
        try:
            download_url_to_file(candidate_url, raw_path, bvid)
            break
        except Exception as exc:
            download_errors.append(str(exc))
            logger.warning("Audio CDN failed (%s); trying next source if available…", exc)
    else:
        raise RuntimeError("all DASH audio sources failed: " + " | ".join(download_errors))
    logger.info("Transcoding to MP3…")
    transcode_to_mp3(raw_path, mp3_path, bitrate=bitrate)
    try:
        raw_path.unlink(missing_ok=True)
    except OSError:
        pass
    return mp3_path


def _guess_suffix(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".m4a", ".mp4", ".aac", ".opus", ".mp3"):
        if path.endswith(ext):
            return ext
    return ".bin"


def download_audio_via_ytdlp(
    bvid: str,
    page: int,
    out_mp3: Path,
    cookies_from_browser: Optional[str] = None,
) -> None:
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    url = f"{video_page_url(bvid)}?p={page}"
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        str(out_mp3.with_suffix(".%(ext)s")),
        url,
    ]
    if cookies_from_browser:
        cmd[1:1] = ["--cookies-from-browser", cookies_from_browser]
    logger.info("Running yt-dlp fallback…")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip().splitlines()
        useful = "\n".join(details[-8:])
        raise RuntimeError(f"yt-dlp audio fallback failed:\n{useful}")


def resolve_mp3_after_ytdlp(out_mp3: Path) -> Path:
    """yt-dlp may name file .mp3 directly; if template was used, pick newest mp3 in dir."""
    if out_mp3.exists():
        return out_mp3
    parent = out_mp3.parent
    pattern = out_mp3.stem + "*"
    candidates = sorted(parent.glob(pattern + ".mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    # any mp3 in parent matching stem
    for p in sorted(parent.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
        return p
    raise FileNotFoundError(f"No mp3 produced next to {out_mp3}")


def download_part_mp3(
    bvid: str,
    page: int,
    cid: int,
    out_dir: Path,
    prefer_ytdlp: bool = False,
    cookies_from_browser: Optional[str] = None,
) -> Path:
    """
    page: 1-based index.
    Writes ``{bvid}_p{page}.mp3`` into out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{bvid}_p{page}"
    out_mp3 = out_dir / f"{base}.mp3"

    if prefer_ytdlp:
        download_audio_via_ytdlp(bvid, page, out_mp3, cookies_from_browser=cookies_from_browser)
        return resolve_mp3_after_ytdlp(out_mp3)

    try:
        return download_audio_via_api(bvid, cid, out_dir, basename=base)
    except Exception as e:
        logger.warning("API download failed (%s), trying yt-dlp…", e)
        download_audio_via_ytdlp(bvid, page, out_mp3, cookies_from_browser=cookies_from_browser)
        return resolve_mp3_after_ytdlp(out_mp3)
