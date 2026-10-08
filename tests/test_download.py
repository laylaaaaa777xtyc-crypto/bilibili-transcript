from types import SimpleNamespace

import pytest
import requests

from bilibili_transcript.download import download_audio_via_ytdlp, download_url_to_file


class FakeStreamResponse:
    def __init__(self, chunks, *, status_code=200, headers=None):
        self.chunks = chunks
        self.status_code = status_code
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


def test_large_download_resumes_after_connection_break(tmp_path, monkeypatch):
    destination = tmp_path / "audio.bin"
    destination.write_bytes(b"abc")
    responses = iter(
        [
            FakeStreamResponse(
                [b"a"],
                status_code=206,
                headers={"Content-Length": "1", "Content-Range": "bytes 0-0/6"},
            ),
            FakeStreamResponse(
                [b"d", requests.exceptions.ChunkedEncodingError("connection broke")],
                status_code=206,
                headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
            ),
            FakeStreamResponse(
                [b"def"],
                status_code=206,
                headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
            ),
        ]
    )
    ranges = []

    def fake_get(*args, **kwargs):
        ranges.append(kwargs["headers"].get("Range"))
        return next(responses)

    monkeypatch.setattr("bilibili_transcript.download.requests.get", fake_get)
    monkeypatch.setattr("bilibili_transcript.download.time.sleep", lambda _seconds: None)

    download_url_to_file("https://example.test/audio", destination, "BV1f3DYBDE9h")
    assert destination.read_bytes() == b"abcdef"
    assert ranges == ["bytes=0-0", "bytes=3-5", "bytes=3-5"]


def test_ytdlp_error_includes_actual_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bilibili_transcript.download.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: HTTP Error 412: Precondition Failed",
        ),
    )
    with pytest.raises(RuntimeError, match="HTTP Error 412"):
        download_audio_via_ytdlp(
            "BV1f3DYBDE9h",
            1,
            tmp_path / "audio.mp3",
        )
