import json

import requests

from bilibili_transcript.meta import fetch_video_meta


VIDEO_ID = "BV1f3DYBDE9h"


class FakeResponse:
    def __init__(self, *, data=None, text="", error=None):
        self._data = data
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self._data


def test_view_api_412_falls_back_to_public_video_page(monkeypatch):
    video_data = {
        "bvid": VIDEO_ID,
        "aid": 123,
        "cid": 456,
        "title": "页面内嵌标题",
        "duration": 60,
        "pages": [{"cid": 456, "page": 1, "duration": 60}],
    }
    page = (
        "<html><script>window.__INITIAL_STATE__="
        + json.dumps({"videoData": video_data}, ensure_ascii=False)
        + ";</script></html>"
    )
    responses = iter(
        [
            FakeResponse(error=requests.HTTPError("412 Precondition Failed")),
            FakeResponse(text=page),
        ]
    )
    monkeypatch.setattr("bilibili_transcript.meta.requests.get", lambda *args, **kwargs: next(responses))

    result = fetch_video_meta(VIDEO_ID)
    assert result["title"] == "页面内嵌标题"
    assert result["aid"] == 123
    assert result["pages"][0]["cid"] == 456
