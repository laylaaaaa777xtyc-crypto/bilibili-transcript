from bilibili_transcript.models import Transcript
from bilibili_transcript.processor import MockLLMClient, LLMProcessor, RuleBasedProcessor


def _transcript(segments):
    return Transcript(video_id="BV_test", title="测试标题", segments=segments)


def test_short_subtitles_are_merged():
    result = RuleBasedProcessor().process(
        _transcript(
            [
                {"start": 0, "end": 1, "text": "这是"},
                {"start": 1, "end": 2, "text": "一条"},
                {"start": 2, "end": 3, "text": "短字幕。"},
            ]
        )
    )
    assert result.paragraphs == ["这是一条短字幕。"]


def test_consecutive_duplicate_sentences_are_removed():
    result = RuleBasedProcessor().process(
        _transcript(
            [
                {"start": 0, "end": 1, "text": "重复句。"},
                {"start": 1, "end": 2, "text": "重复句。"},
                {"start": 2, "end": 3, "text": "下一句。"},
            ]
        )
    )
    assert result.text.count("重复句。") == 1
    assert "下一句。" in result.text


def test_llm_processor_uses_provider_neutral_client():
    client = MockLLMClient("第一段。\n\n第二段。")
    result = LLMProcessor(client).process(
        _transcript([{"start": 0, "end": 1, "text": "原文。"}])
    )
    assert result.paragraphs == ["第一段。", "第二段。"]
