from datetime import datetime, timezone

import pytest

from marginalis.ingestion import eia


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self._body, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Serves `total` synthetic rows in pages of at most `page` rows."""

    def __init__(self, total, page, fail_first=0):
        self.total, self.page, self.fail_first = total, page, fail_first
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        if self.fail_first:
            self.fail_first -= 1
            return FakeResponse({}, status=503)
        off = params["offset"]
        rows = [{"period": str(i)} for i in range(off, min(off + self.page, self.total))]
        return FakeResponse({"response": {"total": str(self.total), "data": rows}})


def test_paginates_until_total():
    s = FakeSession(total=12_345, page=5000)
    rows = list(eia.paginate("region-data", {}, session=s, key="k"))
    assert [r["period"] for r in rows] == [str(i) for i in range(12_345)]
    assert [c["offset"] for c in s.calls] == [0, 5000, 10000]


def test_short_pages_still_reach_total():
    # The API may return fewer rows than requested; offsets must follow rows received.
    s = FakeSession(total=7, page=3)
    assert len(list(eia.paginate("region-data", {}, session=s, key="k"))) == 7
    assert [c["offset"] for c in s.calls] == [0, 3, 6]


def test_empty_result():
    s = FakeSession(total=0, page=5000)
    assert list(eia.paginate("region-data", {}, session=s, key="k")) == []


def test_retries_server_errors(monkeypatch):
    monkeypatch.setattr(eia.time, "sleep", lambda _: None)
    s = FakeSession(total=3, page=5000, fail_first=2)
    assert len(list(eia.paginate("region-data", {}, session=s, key="k"))) == 3
    assert len(s.calls) == 3


def test_empty_page_before_total_raises():
    class Truncating(FakeSession):
        def get(self, url, params, timeout):
            resp = super().get(url, params, timeout)
            if params["offset"] > 0:
                resp._body["response"]["data"] = []
            return resp

    with pytest.raises(RuntimeError, match="empty page"):
        list(eia.paginate("region-data", {}, session=Truncating(10, 5), key="k"))


def test_month_starts_crosses_year():
    utc = timezone.utc
    ms = eia.month_starts(datetime(2019, 11, 15, tzinfo=utc), datetime(2020, 2, 1, tzinfo=utc))
    assert [f"{m:%Y-%m}" for m in ms] == ["2019-11", "2019-12", "2020-01"]
