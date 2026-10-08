import argparse

import pytest

from bilibili_transcript.providers import detect_provider
from bilibili_transcript.providers.bilibili import BilibiliProvider
from bilibili_transcript.providers.base import VideoMeta


class TestBilibiliProviderMatch:
    def test_bvid(self):
        p = BilibiliProvider()
        assert p.match("BV1f3DYBDE9h")

    def test_url(self):
        p = BilibiliProvider()
        assert p.match("https://www.bilibili.com/video/BV1f3DYBDE9h")

    def test_b23(self):
        p = BilibiliProvider()
        assert p.match("https://b23.tv/abc123")

    def test_no_match(self):
        p = BilibiliProvider()
        assert not p.match("https://youtube.com/watch?v=abc")


class TestDetectProvider:
    def test_bilibili(self):
        p = detect_provider("BV1f3DYBDE9h")
        assert p.name == "bilibili"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="No provider matched"):
            detect_provider("https://youtube.com/watch?v=abc")


def test_invalid_official_subtitles_fall_back_to_asr(monkeypatch):
    provider = BilibiliProvider()
    meta = VideoMeta(
        video_id="BV1f3DYBDE9h",
        title="fixture",
        aid=1,
        pages=[{"cid": 1, "duration": 1800}],
    )
    monkeypatch.setattr(
        "bilibili_transcript.providers.bilibili.try_fetch_official_segments",
        lambda *args, **kwargs: (
            [{"start": 0, "end": 1, "text": "太短了"}],
            "太短了",
            {"lan": "zh-CN", "subtitle_url": "fixture"},
        ),
    )
    args = argparse.Namespace(
        force_asr=False,
        prefer_subtitles=True,
        cookies_from_browser=None,
        ytdlp_subs=False,
    )

    assert provider.fetch_segments(meta, 1, 1, args=args) is None
