import json

from bilibili_transcript import cli
from bilibili_transcript.formatters import format_article_markdown, format_srt, format_txt
from bilibili_transcript.models import Transcript
from bilibili_transcript.processor import RuleBasedProcessor


VIDEO_ID = "BV1f3DYBDE9h"


def _data():
    return {
        "video_id": VIDEO_ID,
        "bvid": VIDEO_ID,
        "title": "可读文稿测试",
        "text": "你好世界。下一句。",
        "segments": [
            {"id": 0, "start": 0, "end": 1, "text": "你好 世界。"},
            {"id": 1, "start": 1, "end": 2, "text": "下一句。"},
        ],
    }


def test_txt_has_no_timestamps_and_cleans_spaces():
    processed = RuleBasedProcessor().process(Transcript.from_dict(_data()))
    output = format_txt(processed)
    assert "00:00" not in output
    assert "你好世界。" in output
    assert output.endswith("\n")


def test_srt_keeps_timestamps():
    output = format_srt(_data()["segments"])
    assert "00:00:00,000 --> 00:00:01,000" in output


def test_article_markdown_has_title_and_body():
    processed = RuleBasedProcessor().process(Transcript.from_dict(_data()))
    output = format_article_markdown(processed)
    assert output.startswith("# 可读文稿测试")
    assert "你好世界。" in output


def test_article_cli_uses_cached_transcript(tmp_path, monkeypatch):
    out_dir = tmp_path / VIDEO_ID
    out_dir.mkdir()
    (out_dir / "transcript.json").write_text(
        json.dumps(_data(), ensure_ascii=False), encoding="utf-8"
    )

    class CacheOnlyProvider:
        def extract_id(self, _value):
            return VIDEO_ID

        def fetch_metadata(self, _video_id):
            raise AssertionError("article generation should use cache")

    monkeypatch.setattr(cli, "detect_provider", lambda _value: CacheOnlyProvider())
    assert cli.main([VIDEO_ID, "--output", str(tmp_path), "--article"]) == 0
    article = (out_dir / "article.md").read_text(encoding="utf-8")
    assert "# 可读文稿测试" in article
