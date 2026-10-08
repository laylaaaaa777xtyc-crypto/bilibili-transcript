import json
import time

from fastapi.testclient import TestClient

from bilibili_transcript.web import JobManager, create_app


VIDEO_ID = "BV1f3DYBDE9h"


def _write_result(root):
    directory = root / VIDEO_ID
    directory.mkdir(parents=True, exist_ok=True)
    transcript = {
        "video_id": VIDEO_ID,
        "bvid": VIDEO_ID,
        "title": "Web 测试视频",
        "segments": [{"id": 0, "start": 0, "end": 1, "text": "测试正文。"}],
        "part_sources": [{"part": 1, "mode": "official_cc"}],
    }
    (directory / "transcript.json").write_text(
        json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "article.md").write_text("# Web 测试视频\n\n测试正文。\n", encoding="utf-8")
    return directory


class FakeProcess:
    def __init__(self, command, result_root):
        self.command = command
        self.stdout = iter(["检查字幕\n", "✓ 保存 Transcript\n"])
        self.result_root = result_root

    def wait(self):
        _write_result(self.result_root)
        return 0


def test_build_command_reuses_cli_options(tmp_path):
    manager = JobManager(tmp_path)
    video_id, command = manager.build_command(
        {
            "url": f"https://www.bilibili.com/video/{VIDEO_ID}",
            "article": True,
            "refresh": True,
            "force_asr": True,
            "model": "small",
            "device": "cpu",
            "cookies_from_browser": "chrome",
        }
    )
    assert video_id == VIDEO_ID
    assert "--article" in command
    assert "--skip-download" in command
    assert "--refresh" in command
    assert "--force-asr" in command
    assert command[command.index("--model") + 1] == "small"
    assert command[command.index("--cookies-from-browser") + 1] == "chrome"


def test_background_job_completes_and_lists_files(tmp_path):
    manager = JobManager(
        tmp_path,
        process_factory=lambda command, **kwargs: FakeProcess(command, tmp_path),
    )
    job = manager.start({"url": VIDEO_ID, "article": True})
    deadline = time.time() + 2
    while job.status not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.01)
    assert job.status == "completed"
    assert "transcript.json" in job.files
    assert "article.md" in job.files


def test_web_api_and_static_frontend(tmp_path):
    _write_result(tmp_path)
    manager = JobManager(tmp_path)
    client = TestClient(create_app(tmp_path, manager=manager))

    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/favicon.ico").status_code == 204
    index = client.get("/")
    assert index.status_code == 200
    assert "BiliScribe" in index.text

    results = client.get("/api/results").json()["items"]
    assert results[0]["video_id"] == VIDEO_ID
    detail = client.get(f"/api/results/{VIDEO_ID}").json()
    assert detail["title"] == "Web 测试视频"
    assert "测试正文" in detail["preview"]

    download = client.get(f"/api/results/{VIDEO_ID}/files/article.md")
    assert download.status_code == 200
    assert "测试正文" in download.text
    assert client.get(f"/api/results/{VIDEO_ID}/files/.env").status_code == 404


def test_invalid_job_request_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/jobs", json={"url": "not-a-bilibili-url"})
    assert response.status_code == 400
