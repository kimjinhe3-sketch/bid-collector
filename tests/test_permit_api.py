"""Tests for collectors.permit_api (ArchPmsHubService)."""
from collectors import permit_api


def _fixture_response():
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {
                "totalCount": 2,
                "pageNo": 1,
                "numOfRows": 100,
                "items": {
                    "item": [
                        {
                            "rnum": 1,
                            "mgmPmsrgstPk": "10242010",
                            "platPlc": "서울특별시 강남구 역삼동 775-4",
                            "newPlatPlc": "서울특별시 강남구 테헤란로 123",
                            "sigunguCd": "11680",
                            "bjdongCd": "10100",
                            "bldNm": "역삼빌딩",
                            "mainPurpsCdNm": "업무시설",
                            "strctCdNm": "철근콘크리트구조",
                            "roofCdNm": "평슬래브",
                            "platArea": "1500.50",
                            "archArea": "900.25",
                            "totArea": "12500.75",
                            "bcRat": "60.0",
                            "vlRat": "800.5",
                            "grndFlrCnt": "15",
                            "ugrndFlrCnt": "3",
                            "heit": "55.5",
                            "hhldCnt": "0",
                            "fmlyCnt": "0",
                            "pmsDay": "20250415",
                            "stcnsDay": "20250601",
                            "useAprDay": "",
                            "crtnDay": "20250416",
                        },
                        {
                            "rnum": 2,
                            "mgmPmsrgstPk": "10242011",
                            "platPlc": "서울특별시 강남구 역삼동 123",
                            "sigunguCd": "11680",
                            "bjdongCd": "10100",
                            "bldNm": "",
                            "mainPurpsCdNm": "공동주택",
                            "strctCdNm": "철근콘크리트구조",
                            "platArea": "",
                            "archArea": None,
                            "totArea": "2500.00",
                            "grndFlrCnt": "5",
                            "ugrndFlrCnt": "1",
                            "hhldCnt": "20",
                            "pmsDay": "20250320",
                            "stcnsDay": "",
                            "useAprDay": "20260101",
                        },
                    ],
                },
            },
        }
    }


def _empty_response():
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {"totalCount": 0, "pageNo": 1, "numOfRows": 100,
                     "items": ""},
        }
    }


def test_collect_returns_normalized_rows():
    calls = []
    def fake_client(url, params, **kw):
        calls.append(params)
        return _fixture_response()

    rows = permit_api.collect(
        service_key="TEST", sigungu_cd="11680", bjdong_cd="10100",
        max_pages=1, sleep_seconds=0, http_client=fake_client,
    )
    assert len(rows) == 2
    assert rows[0]["bld_nm"] == "역삼빌딩"
    assert rows[0]["plat_plc"].startswith("서울특별시")
    assert rows[0]["tot_area"] == 12500.75
    assert rows[0]["grnd_flr_cnt"] == 15
    assert rows[0]["pms_day"] == "2025-04-15"
    assert rows[0]["stcns_day"] == "2025-06-01"
    assert rows[0]["use_apr_day"] is None
    assert rows[0]["sigungu_cd"] == "11680"
    assert rows[0]["bjdong_cd"] == "10100"

    # empty numeric strings → None
    assert rows[1]["plat_area"] is None
    assert rows[1]["arch_area"] is None
    assert rows[1]["stcns_day"] is None
    assert rows[1]["use_apr_day"] == "2026-01-01"


def test_collect_stops_when_items_empty():
    calls = []
    def fake(url, params, **kw):
        calls.append(params)
        return _empty_response()

    rows = permit_api.collect(
        service_key="K", sigungu_cd="11680", bjdong_cd="10100",
        max_pages=5, sleep_seconds=0, http_client=fake,
    )
    assert rows == []
    # should only make a single request since items was empty
    assert len(calls) == 1


def test_collect_paginates_until_totalcount_reached():
    call_log = []

    def fake(url, params, **kw):
        call_log.append(int(params["pageNo"]))
        # pretend each page returns 100 rows, totalCount=250 → need 3 pages
        items = [{"rnum": i, "mgmPmsrgstPk": f"PK{params['pageNo']}-{i}",
                  "platPlc": "X", "bldNm": "", "pmsDay": "20250101"}
                 for i in range(100 if int(params["pageNo"]) < 3 else 50)]
        return {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": {"totalCount": 250, "pageNo": int(params["pageNo"]),
                         "numOfRows": 100, "items": {"item": items}},
            }
        }

    rows = permit_api.collect(
        service_key="K", sigungu_cd="11680", bjdong_cd="10100",
        page_size=100, max_pages=10, sleep_seconds=0, http_client=fake,
    )
    assert call_log == [1, 2, 3]
    assert len(rows) == 250


def test_collect_requires_region_codes():
    # missing bjdong_cd → empty list, no http call
    def fake(url, params, **kw):
        raise AssertionError("should not be called")
    rows = permit_api.collect(
        service_key="K", sigungu_cd="11680", bjdong_cd="",
        http_client=fake, sleep_seconds=0,
    )
    assert rows == []


def test_collect_passes_date_params_when_provided():
    captured = {}
    def fake(url, params, **kw):
        captured.update(params)
        return _empty_response()
    permit_api.collect(
        service_key="K", sigungu_cd="11680", bjdong_cd="10100",
        start_date="20250101", end_date="20250601",
        max_pages=1, sleep_seconds=0, http_client=fake,
    )
    assert captured["startDate"] == "20250101"
    assert captured["endDate"] == "20250601"


def test_collect_handles_single_item_as_dict():
    """Some data.go.kr endpoints return items.item as a single dict when
    there is exactly one result, not a list. Ensure it's coerced."""
    def fake(url, params, **kw):
        return {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": {"totalCount": 1, "pageNo": 1, "numOfRows": 100,
                         "items": {"item": {
                             "rnum": 1, "mgmPmsrgstPk": "SOLO",
                             "platPlc": "x", "bldNm": "솔로빌딩",
                             "pmsDay": "20250501",
                         }}},
            }
        }
    rows = permit_api.collect(
        service_key="K", sigungu_cd="11680", bjdong_cd="10100",
        max_pages=1, sleep_seconds=0, http_client=fake,
    )
    assert len(rows) == 1
    assert rows[0]["bld_nm"] == "솔로빌딩"
    assert rows[0]["mgm_pk"] == "SOLO"
