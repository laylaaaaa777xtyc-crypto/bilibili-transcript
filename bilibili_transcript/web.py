"""Local web UI and API layered on top of the existing CLI pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from bilibili_transcript.bvid import extract_bvid

STATIC_DIR = Path(__file__).with_name("web_static")
DOWNLOADABLE_FILES = {
    "metadata.json",
    "transcript.json",
    "transcript.txt",
    "transcript.md",
    "transcript.srt",
    "article.md",
}


class JobPayload(BaseModel):
    url: str
    article: bool = True
    refresh: bool = False
    force_asr: bool = False
    model: str = "small"
    device: str = "auto"
    cookies_from_browser: str = ""


@dataclass
class Job:
    id: str
    video_id: str
    url: str
    status: str = "queued"
    stage: str = "等待开始"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    return_code: Optional[int] = None
    logs: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    error: str = ""

    def public(self) -> Dict[str, Any]:
        value = asdict(self)
        value["logs"] = self.logs[-80:]
        return value


class JobManager:
    """Run CLI jobs without duplicating transcript pipeline behavior."""

    def __init__(
        self,
        output_root: Path,
        process_factory: Callable[..., Any] = subprocess.Popen,
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.process_factory = process_factory
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def build_command(self, payload: Dict[str, Any]) -> tuple[str, List[str]]:
        url = str(payload.get("url") or "").strip()
        video_id = extract_bvid(url)
        command = [
            sys.executable,
            "-m",
            "bilibili_transcript",
            url,
            "--output",
            str(self.output_root),
            "--skip-download",
        ]
        if payload.get("article", True):
            command.append("--article")
        if payload.get("refresh"):
            command.append("--refresh")
        if payload.get("force_asr"):
            command.append("--force-asr")
        model = str(payload.get("model") or "small")
        if model not in {"tiny", "base", "small", "medium", "large-v3"}:
            raise ValueError("不支持的 Whisper 模型")
        command.extend(["--model", model])
        device = str(payload.get("device") or "auto")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("不支持的运行设备")
        command.extend(["--device", device])
        browser = str(payload.get("cookies_from_browser") or "").strip().lower()
        if browser:
            if browser not in {"chrome", "chromium", "brave", "edge", "firefox", "safari", "opera", "vivaldi"}:
                raise ValueError("不支持的浏览器 Cookie 来源")
            command.extend(["--cookies-from-browser", browser])
        return video_id, command

    def start(self, payload: Dict[str, Any]) -> Job:
        video_id, command = self.build_command(payload)
        job = Job(id=uuid.uuid4().hex[:12], video_id=video_id, url=str(payload["url"]))
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, command), daemon=True).start()
        return job

    def _run(self, job: Job, command: List[str]) -> None:
        job.status = "running"
        job.stage = "正在检查字幕与缓存"
        job.started_at = time.time()
        try:
            process = self.process_factory(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if process.stdout is not None:
                for raw_line in process.stdout:
                    line = raw_line.rstrip()
                    if line:
                        job.logs.append(line)
                        if "faster-whisper" in line or "Transcribing" in line:
                            job.stage = "正在进行语音识别"
                        elif "保存 Transcript" in line or "Wrote" in line:
                            job.stage = "正在保存结果"
            job.return_code = process.wait()
            if job.return_code == 0:
                job.status = "completed"
                job.stage = "处理完成"
                result_dir = self.output_root / job.video_id
                job.files = sorted(
                    path.name for path in result_dir.iterdir()
                    if path.is_file() and path.name in DOWNLOADABLE_FILES
                ) if result_dir.is_dir() else []
            else:
                job.status = "failed"
                job.stage = "处理失败"
                job.error = job.logs[-1] if job.logs else "转写进程异常退出"
        except Exception as exc:
            job.status = "failed"
            job.stage = "处理失败"
            job.error = str(exc)
            job.logs.append(str(exc))
        finally:
            job.finished_at = time.time()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_results(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for directory in self.output_root.iterdir():
            if not directory.is_dir() or not directory.name.startswith("BV"):
                continue
            transcript_path = directory / "transcript.json"
            if not transcript_path.is_file():
                continue
            try:
                data = json.loads(transcript_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            files = sorted(
                path.name for path in directory.iterdir()
                if path.is_file() and path.name in DOWNLOADABLE_FILES
            )
            results.append(
                {
                    "video_id": directory.name,
                    "title": data.get("title") or directory.name,
                    "source": (data.get("part_sources") or [{}])[0].get("mode", "unknown"),
                    "segments": len(data.get("segments") or []),
                    "files": files,
                    "updated_at": transcript_path.stat().st_mtime,
                }
            )
        return sorted(results, key=lambda item: item["updated_at"], reverse=True)

    def result_detail(self, video_id: str) -> Optional[Dict[str, Any]]:
        if extract_bvid(video_id) != video_id:
            return None
        directory = self.output_root / video_id
        transcript_path = directory / "transcript.json"
        if not transcript_path.is_file():
            return None
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        preview_path = directory / "article.md"
        if not preview_path.is_file():
            preview_path = directory / "transcript.txt"
        preview = preview_path.read_text(encoding="utf-8") if preview_path.is_file() else ""
        return {
            "video_id": video_id,
            "title": transcript.get("title") or video_id,
            "preview": preview[:200_000],
            "part_sources": transcript.get("part_sources") or [],
            "segments": len(transcript.get("segments") or []),
            "files": [
                item["files"] for item in self.list_results()
                if item["video_id"] == video_id
            ][0],
        }

    def file_path(self, video_id: str, filename: str) -> Optional[Path]:
        if filename not in DOWNLOADABLE_FILES:
            return None
        if extract_bvid(video_id) != video_id:
            return None
        path = self.output_root / video_id / filename
        return path if path.is_file() else None


def create_app(output_root: Path = Path("outputs"), manager: Optional[JobManager] = None):
    """Application factory kept import-safe for CLI-only users."""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    job_manager = manager or JobManager(output_root)
    app = FastAPI(title="BiliScribe", version="0.4.0", docs_url="/api/docs")
    app.state.job_manager = job_manager
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/jobs", status_code=202)
    def create_job(payload: JobPayload):
        try:
            job = job_manager.start(payload.model_dump() if hasattr(payload, "model_dump") else payload.dict())
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.public()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return job.public()

    @app.get("/api/results")
    def list_results():
        return {"items": job_manager.list_results()}

    @app.get("/api/results/{video_id}")
    def result_detail(video_id: str):
        try:
            detail = job_manager.result_detail(video_id)
        except (ValueError, OSError, json.JSONDecodeError):
            detail = None
        if detail is None:
            raise HTTPException(status_code=404, detail="结果不存在")
        return detail

    @app.get("/api/results/{video_id}/files/{filename}")
    def download_file(video_id: str, filename: str):
        try:
            path = job_manager.file_path(video_id, filename)
        except ValueError:
            path = None
        if path is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(path, filename=filename)

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the local BiliScribe web interface")
    parser.add_argument("--host", default="127.0.0.1", help="Listen host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Listen port (default: 8765)")
    parser.add_argument("--output", default="outputs", help="Transcript output root")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Web dependencies are missing; run: pip install -e .") from exc
    app = create_app(Path(args.output))
    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"BiliScribe is running at {url}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
