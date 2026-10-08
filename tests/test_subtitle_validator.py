from bilibili_transcript.validation import BasicSubtitleValidator


def _segment(index, text="正常字幕内容。"):
    return {"start": index * 2.0, "end": index * 2.0 + 1.5, "text": text}


def test_empty_subtitles_are_invalid():
    result = BasicSubtitleValidator().validate([])
    assert not result.valid
    assert "为空" in result.reason


def test_many_duplicate_lines_are_invalid():
    result = BasicSubtitleValidator().validate(
        [_segment(index, "完全重复的一句话。") for index in range(10)]
    )
    assert not result.valid
    assert "重复" in result.reason


def test_abnormal_timestamps_are_invalid():
    segments = [_segment(0), {"start": 5, "end": 3, "text": "时间错误字幕。"}]
    result = BasicSubtitleValidator().validate(segments)
    assert not result.valid
    assert "时间戳" in result.reason


def test_long_video_with_too_little_text_is_invalid():
    result = BasicSubtitleValidator().validate(
        [_segment(0, "这段字幕太短，无法覆盖一部长视频。")], video_duration=1800
    )
    assert not result.valid
    assert "视频很长" in result.reason


def test_normal_subtitles_are_valid():
    segments = [_segment(i, f"这是第{i}条正常且各不相同的字幕内容。") for i in range(20)]
    result = BasicSubtitleValidator().validate(segments, video_duration=40)
    assert result.valid
    assert result.confidence >= 0.9
