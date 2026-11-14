"""Tests for the web page's server (web.py). No internet needed.

Run with:  python -m pytest -q
"""
import json
import urllib.error
import urllib.request

import pytest

import web


@pytest.fixture(scope="module")
def base_url():
    server = web.start_in_background(port=0)      # 0 = any free port
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def post(base_url, payload, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    request = urllib.request.Request(
        base_url + "/api/split", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


SHIFT = {
    "total": 350,
    "people": [
        {"name": "Anna", "hours": 8, "dept": "Kitchen", "share": "full"},
        {"name": "Cem", "hours": 6, "dept": "Kitchen", "share": "full"},
        {"name": "Ben", "hours": 7.5, "dept": "Service", "share": "full"},
    ],
}


def test_page_and_logo_are_served(base_url):
    with urllib.request.urlopen(base_url + "/", timeout=5) as response:
        assert response.status == 200
        assert b"Start today" in response.read()
    with urllib.request.urlopen(base_url + "/logo.png", timeout=5) as response:
        assert response.headers["Content-Type"] == "image/png"


def test_other_files_are_not_served(base_url):
    for path in ("/bot.py", "/.env", "/../bot.py", "/web.py"):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base_url + path, timeout=5)
        assert error.value.code == 404


def test_split_matches_the_bot(base_url):
    status, result = post(base_url, SHIFT)
    assert status == 200
    assert result["total"] == 350
    tips = {p["name"]: p["tips"] for p in result["people"]}
    assert tips == {"Anna": 100.0, "Cem": 75.0, "Ben": 175.0}


def test_half_share(base_url):
    shift = json.loads(json.dumps(SHIFT))
    shift["people"][1].update(hours=8, share="half")
    status, result = post(base_url, shift)
    tips = {p["name"]: p["tips"] for p in result["people"]}
    assert status == 200
    assert tips["Anna"] == pytest.approx(116.67)
    assert tips["Cem"] == pytest.approx(58.33)


@pytest.mark.parametrize("change, message", [
    ({"total": 0}, "more than zero"),
    ({"total": "350"}, "must be a number"),
    ({"total": True}, "must be a number"),
    ({"total": 1e12}, "too high"),
    ({"people": []}, "at least one person"),
    ({"people": [{"name": "Anna", "hours": 8, "dept": "Kitchen"}]}, "Service"),
    ({"people": [{"name": " ", "hours": 8, "dept": "Kitchen"}]}, "needs a name"),
    ({"people": [{"name": "Anna", "hours": 99, "dept": "Kitchen"}]}, "too high"),
    ({"people": [{"name": "Anna", "hours": 8, "dept": "Bar"}]}, "department"),
])
def test_bad_input_gets_a_clear_message(base_url, change, message):
    status, result = post(base_url, {**SHIFT, **change})
    assert status == 400
    assert message in result["error"]


def test_garbage_and_oversized_requests_are_rejected(base_url):
    assert post(base_url, None, raw=b"not json")[0] == 400
    assert post(base_url, None, raw=b"[1, 2, 3]")[0] == 400
    assert post(base_url, None, raw=b'{"total": NaN, "people": []}')[0] == 400
    assert post(base_url, None, raw=b"x" * 50_000)[0] == 400
