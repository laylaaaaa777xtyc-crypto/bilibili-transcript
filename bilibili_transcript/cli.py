#!/usr/bin/env python3
"""CLI: video URL → reliable raw transcript → readable local exports."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.tree import Tree

from bilibili_transcript.cache import load_cached_transcript
from bilibili_transcript.draft_md import build_draft_transcript_markdown
from bilibili_transcript.finalize_md import write_eval_markdown_from_json
from bilibili_transcript.formatters import format_article_markdown, format_srt, format_txt
from bilibili_transcript.models import Transcript
from bilibili_transcript.processor import RuleBasedProcessor
from bilibili_transcript.providers import detect_provider
from bilibili_transcript.providers.base import SourceRecord, VideoMeta
from bilibili_transcript.transcribe import save_transcript_json, transcribe_mp3

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
console = Console()


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def resolve_compute_type(compute_type: str, device: str) -> str:
    if compute_type != "default":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def merge_segment_lists(
    part_segments: List[List[Dict[str, Any]]],
    part_indices: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    new_id = 0
    indices = part_indices or list(range(1, len(part_segments) + 1))
    for part_idx, segs in zip(indices, part_segments):
        for segment in segs:
            merged.append(
                {
                    "id": new_id,
                    "start": float(segment.get("start", 0)),
                    "end": float(segment.get("end", 0)),
                    "text": (segment.get("text") or "").strip(),
                    "words": segment.get("words"),
                    "part": part_idx,
                    "text_source": segment.get("source") or segment.get("text_source"),
                }
            )
            new_id += 1
    return merged


def obtain_part_segments(
    *,
    meta: VideoMeta,
    part_index: int,
    cid: int,
    out_dir: Path,
    args: argparse.Namespace,
    device: str,
    compute_type: str,
    provider: Any,
) -> Tuple[List[Dict[str, Any]], str, SourceRecord]:
    """Return (segments, full_text, source_record)."""
    result = provider.fetch_segments(meta, part_index, cid, args=args)
    if result is not None:
        return result

    console.print("[yellow]! 未找到可靠字幕[/yellow]")
    console.print("[cyan]→ 下载音频[/cyan]")
    mp3 = out_dir / f"{meta.video_id}_p{part_index}.mp3"
    if args.skip_download and mp3.exists():
        logger.info("Using existing %s", mp3)
    else:
        mp3 = provider.download_audio(meta, part_index, cid, out_dir, args=args)

    console.print("[cyan]→ faster-whisper 转写[/cyan]")
    console.print(f"  Model: {args.whisper_model}\n  Device: {device}")
    transcript = transcribe_mp3(
        mp3,
        model_size=args.whisper_model,
        device=device,
        compute_type=compute_type,
        language=args.language,
        vad_filter=not args.no_vad,
    )
    segments = transcript.get("segments") or []
    text = transcript.get("text") or ""
    return segments, text, SourceRecord(
        part=part_index,
        mode="asr",
        extra={"whisper_model": args.whisper_model},
    )


def _resolve_output_dir(args: argparse.Namespace, video_id: str) -> Tuple[Path, bool]:
    """Return output directory and whether legacy direct-output mode was requested."""
    if args.out_dir:
        return Path(args.out_dir).expanduser().resolve(), True
    return (Path(args.output).expanduser() / video_id).resolve(), False


def _metadata_dict(meta: VideoMeta, source: str) -> Dict[str, Any]:
    owner = meta.extra.get("owner") or {}
    return {
        "source": source,
        "video_id": meta.video_id,
        "bvid": meta.video_id,
        "title": meta.title,
        "aid": meta.aid,
        "owner": owner,
        "duration": meta.extra.get("duration"),
        "description": meta.extra.get("desc"),
        "pages": meta.pages,
    }


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_outputs(
    transcript_data: Dict[str, Any],
    out_dir: Path,
    args: argparse.Namespace,
    *,
    legacy_mode: bool,
) -> List[Path]:
    """Write raw and derived files. Raw segments are never modified in place."""
    out_dir.mkdir(parents=True, exist_ok=True)
    video_id = str(transcript_data.get("video_id") or transcript_data.get("bvid"))
    json_path = out_dir / "transcript.json"
    save_transcript_json(transcript_data, json_path)
    written = [json_path]

    legacy_json = out_dir / f"{video_id}_transcript.json"
    if legacy_mode:
        save_transcript_json(transcript_data, legacy_json)
        written.append(legacy_json)

    if args.json_only:
        return written

    transcript = Transcript.from_dict(transcript_data)
    processed = RuleBasedProcessor().process(transcript)
    txt_path = out_dir / "transcript.txt"
    txt_path.write_text(format_txt(processed), encoding="utf-8")
    written.append(txt_path)

    md = build_draft_transcript_markdown(
        transcript.title,
        transcript.segments,
        max_span_seconds=args.chunk_span,
    )
    md_path = out_dir / "transcript.md"
    md_path.write_text(md, encoding="utf-8")
    written.append(md_path)

    srt_path = out_dir / "transcript.srt"
    srt_path.write_text(format_srt(transcript.segments), encoding="utf-8")
    written.append(srt_path)

    if args.article:
        article_path = out_dir / "article.md"
        article_path.write_text(format_article_markdown(processed), encoding="utf-8")
        written.append(article_path)

    if legacy_mode:
        legacy_md = out_dir / f"{video_id}_transcript.md"
        legacy_md.write_text(md, encoding="utf-8")
        written.append(legacy_md)
        try:
            written.append(write_eval_markdown_from_json(legacy_json))
        except Exception as exc:
            logger.warning("Skipped legacy structured markdown: %s", exc)
    return written


def _show_output_tree(out_dir: Path, paths: List[Path]) -> None:
    tree = Tree(str(out_dir))
    for path in paths:
        if path.parent == out_dir:
            tree.add(path.name)
    console.print("\n[bold]输出：[/bold]")
    console.print(tree)


def run_pipeline(args: argparse.Namespace) -> int:
    console.print("\n[bold cyan]Bilibili Transcript[/bold cyan]\n")
    provider = detect_provider(args.input)
    video_id = provider.extract_id(args.input)
    out_dir, legacy_mode = _resolve_output_dir(args, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.refresh:
        cached = load_cached_transcript(out_dir, video_id)
        if cached is not None:
            console.print(f"[green]✓[/green] 命中缓存  {out_dir / 'transcript.json'}")
            written = _write_outputs(cached, out_dir, args, legacy_mode=legacy_mode)
            if not args.json_only:
                metadata = cached.get("metadata") or {
                    "source": cached.get("source"),
                    "video_id": video_id,
                    "bvid": cached.get("bvid") or video_id,
                    "title": cached.get("title"),
                }
                metadata_path = out_dir / "metadata.json"
                _write_json(metadata_path, metadata)
                written.insert(0, metadata_path)
            if args.article:
                console.print("[green]✓[/green] 生成文稿")
            _show_output_tree(out_dir, written)
            return 0

    try:
        meta = provider.fetch_metadata(video_id)
    except Exception as exc:
        logger.error("Failed to fetch metadata: %s", exc)
        return 5

    if not meta.aid and provider.name == "bilibili":
        logger.warning("无法获取 aid，将跳过官方字幕并继续尝试 yt-dlp 字幕或 ASR。")

    owner = (meta.extra.get("owner") or {}).get("name") or "未知"
    duration = int(meta.extra.get("duration") or 0)
    console.print(
        f"[green]✓[/green] 解析视频\n  {meta.title}\n  UP主：{owner}\n"
        f"  时长：{duration // 60:02d}:{duration % 60:02d}"
    )

    try:
        pages_sel, page_indices = provider.page_indices(meta, args.part)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    device = resolve_device(args.device)
    compute_type = resolve_compute_type(args.compute_type, device)
    all_segment_lists: List[List[Dict[str, Any]]] = []
    sources: List[Dict[str, Any]] = []

    for part_index, page in zip(page_indices, pages_sel):
        cid = int(page.get("cid", 0))
        segments, _text, source = obtain_part_segments(
            meta=meta,
            part_index=part_index,
            cid=cid,
            out_dir=out_dir,
            args=args,
            device=device,
            compute_type=compute_type,
            provider=provider,
        )
        all_segment_lists.append(segments)
        sources.append(source.to_dict())
        if source.mode != "asr":
            validation = source.extra.get("validation") or {}
            console.print(f"[green]✓[/green] 检查官方字幕  找到 {len(segments)} 条字幕")
            console.print(
                f"[green]✓[/green] 字幕质量检测  Confidence: "
                f"{float(validation.get('confidence', 0.0)):.0%}"
            )

    merged_segments = merge_segment_lists(all_segment_lists, page_indices)
    if not merged_segments:
        logger.error("No segments produced (subtitles and ASR both empty). Try --no-vad or check the video.")
        return 4

    metadata = _metadata_dict(meta, provider.name)
    transcript_data: Dict[str, Any] = {
        "source": provider.name,
        "video_id": video_id,
        "bvid": video_id,
        "title": meta.title,
        "text": "".join((segment.get("text") or "") for segment in merged_segments),
        "segments": merged_segments,
        "part_sources": sources,
        "metadata": metadata,
    }
    written = _write_outputs(transcript_data, out_dir, args, legacy_mode=legacy_mode)
    console.print("[green]✓[/green] 保存 Transcript")

    if not args.json_only:
        metadata_path = out_dir / "metadata.json"
        _write_json(metadata_path, metadata)
        written.insert(0, metadata_path)
    if args.article:
        console.print("[green]✓[/green] 生成文稿")
    _show_output_tree(out_dir, written)
    return 0


def run_export_html(args: argparse.Namespace) -> int:
    from bilibili_transcript.export_html import export_morandi_html

    target = Path(args.input)
    if target.is_dir():
        markdown_files = list(target.glob("*_transcript_成稿.md"))
        if not markdown_files:
            logger.error("No *_transcript_成稿.md found in %s", target)
            return 1
        target = markdown_files[0]
    if not target.is_file():
        logger.error("Not found: %s", target)
        return 1

    output = export_morandi_html(target)
    logger.info("Wrote %s", output)
    if not args.no_open:
        import platform
        import subprocess

        opener = {"Darwin": "open", "Linux": "xdg-open", "Windows": "start"}.get(
            platform.system(), "open"
        )
        try:
            subprocess.Popen([opener, str(output)])
        except Exception:
            pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="bili",
        description="Bilibili URL → high-quality readable transcript (subtitles-first, ASR fallback).",
        epilog='Quick start: bili "https://www.bilibili.com/video/BV..." --article',
    )
    subparsers = root.add_subparsers(dest="command")
    transcript_parser = subparsers.add_parser("transcript", help="Fetch a transcript from a video URL")
    _add_transcript_args(transcript_parser)

    html_parser = subparsers.add_parser("export-html", help="Convert 成稿.md to Morandi HTML")
    html_parser.add_argument("input", help="Path to *_transcript_成稿.md or a directory containing one")
    html_parser.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    return root


def _add_transcript_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="Video URL or ID (e.g. BV号)")
    parser.add_argument(
        "-o",
        "--out-dir",
        default=None,
        help="Legacy direct output directory (kept for compatibility)",
    )
    parser.add_argument(
        "--output",
        default="outputs",
        metavar="DIR",
        help="Output root; files go to DIR/<video_id> (default: outputs)",
    )
    parser.add_argument("--part", type=int, default=None, help="Process only part N (1-based)")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing MP3 (ASR path only)")
    parser.add_argument("--ytdlp", action="store_true", help="Force yt-dlp for audio download")
    parser.add_argument("--ytdlp-subs", action="store_true", help="Try yt-dlp subtitles after official API")
    parser.add_argument(
        "--cookies-from-browser",
        default=None,
        metavar="BROWSER",
        help="Read browser cookies for authenticated requests (e.g. chrome)",
    )
    parser.add_argument(
        "--prefer-subtitles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer reliable subtitles over ASR (default: on)",
    )
    parser.add_argument("--force-asr", action="store_true", help="Skip subtitles and use local ASR")
    parser.add_argument(
        "--model",
        "--whisper-model",
        dest="whisper_model",
        default="medium",
        help="faster-whisper model (small/medium/large-v3)",
    )
    parser.add_argument("--device", default="auto", help="cpu / cuda / auto")
    parser.add_argument("--compute-type", default="default", help="default / int8 / float16 / float32")
    parser.add_argument("--language", default="zh", help="Whisper language code (default: zh)")
    parser.add_argument("--no-vad", action="store_true", help="Disable VAD filter")
    parser.add_argument("--json-only", action="store_true", help="Write transcript JSON only")
    parser.add_argument("--article", action="store_true", help="Generate readable article.md")
    parser.add_argument("--refresh", action="store_true", help="Ignore cached transcript and fetch again")
    parser.add_argument(
        "--chunk-span",
        type=float,
        default=300.0,
        metavar="SEC",
        help="Draft section span in seconds (default: 300)",
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        parser.print_help()
        return 0
    if raw_args[0] in {"-h", "--help"}:
        raw_args.insert(0, "transcript")
    elif raw_args[0] not in {"transcript", "export-html"}:
        raw_args.insert(0, "transcript")
    args = parser.parse_args(raw_args)
    try:
        if args.command == "export-html":
            return run_export_html(args)
        if args.command == "transcript":
            return run_pipeline(args)
        parser.print_help()
        return 0
    except KeyboardInterrupt:
        logger.error("Interrupted")
        return 130
    except Exception as exc:
        logger.exception("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
