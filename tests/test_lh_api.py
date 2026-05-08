"""LH API collector tests (XML parsing, normalization, pagination)."""
from collectors import lh_api


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <bidNum>L26-0001</bidNum>
        <bidnmKor>경기도 화성시 ○○지구 조경공사</bidnmKor>
        <presmtPrc>1500000000</presmtPrc>
        <tndrdocAcptBgninDtm>20260420 10:00</tndrdocAcptBgninDtm>
        <tndrdocAcptEndDtm>20260505 14:00</tndrdocAcptEndDtm>
        <openDtm>20260506 11:00</openDtm>
        <zoneRstrct1>경기도</zoneRstrct1>
        <zoneRstrct2></zoneRstrct2>
        <bidProgrsStatus>공고중</bidProgrsStatus>
      </item>
      <item>
        <bidNum>L26-0002</bidNum>
        <bidnmKor>전국 건설폐기물처리</bidnmKor>
        <presmtPrc></presmtPrc>
        <tndrdocAcptBgninDtm>20260421 10:00</tndrdocAcptBgninDtm>
        <tndrdocAcptEndDtm>20260510 14:00</tndrdocAcptEndDtm>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>2</totalCount>
  </body>
</response>"""


def _client(xml_text):
    calls = []
    def _c(url, params, **kw):
        calls.append({"url": url, **params})
        return xml_text
    _c.calls = calls
    return _c


def test_collect_skips_without_key():
    rows = lh_api.collect(service_key="", http_client=_client(SAMPLE_XML))
    assert rows == []


def test_collect_normalizes_xml():
    client = _client(SAMPLE_XML)
    rows = lh_api.collect(service_key="K", sleep_seconds=0, http_client=client)
    assert len(rows) == 2

    r0 = rows[0]
    assert r0["source"] == "lh_api"
    assert r0["bid_no"] == "L26-0001"
    assert "조경공사" in r0["title"]
    assert r0["estimated_price"] == 1_500_000_000
    assert r0["close_date"] == "20260505 14:00"
    # zoneRstrct1 (경기도) 가 org_name 에 prepend → 시도 추출 시 '경기'
    assert "경기도" in r0["org_name"]
    assert "한국토지주택공사" in r0["org_name"]

    r1 = rows[1]
    assert r1["estimated_price"] is None  # 빈 값


def test_collect_paginates_when_total_exceeds_page_size():
    """totalCount=250, page_size=100 → 3 pages 호출"""
    page1 = SAMPLE_XML.replace("<totalCount>2</totalCount>",
                                "<totalCount>250</totalCount>")
    client = _client(page1)
    rows = lh_api.collect(service_key="K", page_size=100, sleep_seconds=0,
                           http_client=client)
    pages_called = [c.get("pageNo") for c in client.calls]
    assert pages_called == [1, 2, 3]


def test_collect_handles_empty_response():
    empty_xml = """<?xml version="1.0"?>
    <response><body><items></items><totalCount>0</totalCount></body></response>"""
    rows = lh_api.collect(service_key="K", sleep_seconds=0,
                           http_client=_client(empty_xml))
    assert rows == []


def test_collect_passes_date_range():
    captured = {}
    def fake(url, params, **kw):
        captured.update(params)
        return SAMPLE_XML
    lh_api.collect(service_key="K", lookback_days=7, sleep_seconds=0,
                    http_client=fake)
    assert "tndrbidRegDtStart" in captured
    assert "tndrbidRegDtEnd" in captured
    assert len(captured["tndrbidRegDtStart"]) == 8  # YYYYMMDD
    assert len(captured["tndrbidRegDtEnd"]) == 8
