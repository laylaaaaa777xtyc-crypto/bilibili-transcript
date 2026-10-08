import json

from bilibili_transcript import cli
from bilibili_transcript.providers.base import SourceRecord, VideoMeta


VIDEO_ID = "BV1f3DYBDE9h"


def _cached_data():
    return {
        "source": "bilibili",
        "video_id": VIDEO_ID,
        "bvid": VIDEO_ID,
        "title": "缓存视频",
        "text": "缓存内容。",
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.0, "text": "缓存内容。"}
        ],
        "part_sources": [{"part": 1, "mode": "official_cc"}],
    }


class FakeProvider:
    name = "fixture"

    def __init__(self):
        self.fetch_count = 0

    def extract_id(self, _value):
        return VIDEO_ID

    def fetch_metadata(self, _video_id):
        self.fetch_count += 1
        return VideoMeta(
            video_id=VIDEO_ID,
            title="刷新视频",
            aid=1,
            pages=[{"cid": 10, "duration": 10}],
            extra={"duration": 10, "owner": {"name": "测试UP"}},
        )

    def page_indices(self, meta, part):
        return meta.pages, [1]

    def fetch_segments(self, meta, part_index, cid, *, args):
        segments = [{"id": 0, "start": 0, "end": 2, "text": "刷新内容。"}]
        return segments, "刷新内容。", SourceRecord(part=1, mode="fixture")

    def download_audio(self, *args, **kwargs):
        raise AssertionError("fixture should not use ASR")


def test_transcript_cache_hit_skips_network(tmp_path, monkeypatch):
    out_dir = tmp_path / VIDEO_ID
    out_dir.mkdir()
    (out_dir / "transcript.json").write_text(
        json.dumps(_cached_data(), ensure_ascii=False), encoding="utf-8"
    )
    provider = FakeProvider()
    monkeypatch.setattr(cli, "detect_provider", lambda _value: provider)

    assert cli.main([VIDEO_ID, "--output", str(tmp_path)]) == 0
    assert provider.fetch_count == 0
    assert (out_dir / "transcript.txt").exists()


def test_refresh_bypasses_cache(tmp_path, monkeypatch):
    out_dir = tmp_path / VIDEO_ID
    out_dir.mkdir()
    (out_dir / "transcript.json").write_text(
        json.dumps(_cached_data(), ensure_ascii=False), encoding="utf-8"
    )
    provider = FakeProvider()
    monkeypatch.setattr(cli, "detect_provider", lambda _value: provider)

    assert cli.main([VIDEO_ID, "--output", str(tmp_path), "--refresh"]) == 0
    assert provider.fetch_count == 1
    refreshed = json.loads((out_dir / "transcript.json").read_text(encoding="utf-8"))
    assert refreshed["title"] == "刷新视频"
    for name in ("metadata.json", "transcript.txt", "transcript.md", "transcript.srt"):
        assert (out_dir / name).exists()
