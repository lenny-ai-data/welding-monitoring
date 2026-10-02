"""Tests HTTP de l'app (sécurité, routes média, liste blanche). Nécessitent app_data/ généré."""

import pytest

from weldmon.app import data

pytestmark = pytest.mark.skipif(not (data.DATA_DIR / "runs.json").exists(), reason="app_data/ absent")


@pytest.fixture(scope="module")
def client():
    from weldmon.app import create_app

    return create_app().server.test_client()


def test_index_has_security_headers(client):
    r = client.get("/")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "''" not in csp  # hash de scripts correctement quotés
    assert "unsafe-eval" not in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in r.headers  # uniquement derrière HTTPS
    assert "Cross-Origin-Opener-Policy" not in r.headers


def test_hsts_behind_https_proxy(client):
    r = client.get("/healthz", headers={"X-Forwarded-Proto": "https"})
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.data == b"ok"


def test_layout_served(client):
    assert client.get("/_dash-layout").status_code == 200


def test_video_supports_range_requests(client):
    r = client.get("/media/videos/DoE3_19.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert len(r.data) == 100
    assert r.headers["Content-Type"] == "video/mp4"
    assert "max-age" in r.headers["Cache-Control"]


@pytest.mark.parametrize(
    "path",
    [
        "/media/runs.json",
        "/media/../runs.json",
        "/media/%2e%2e/meta.json",
        "/media/videos/../../meta.json",
        "/media/videos/DoE9_1.mp4",
        "/media/videos/DoE3_99.mp4",
        "/media/seg/DoE3_19/gt/000.png",
    ],
)
def test_media_whitelist(client, path):
    assert client.get(path).status_code == 404


def test_overlay_ok(client):
    r = client.get("/overlay/DoE3_19/60.jpg?src=pred&cls=wps&a=55")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/jpeg"
    assert r.data[:2] == b"\xff\xd8"


@pytest.mark.parametrize(
    "path",
    [
        "/overlay/DoE1_1/10.jpg",  # run non annoté
        "/overlay/DoE3_19/999.jpg",  # frame hors bornes
        "/overlay/DoE3_19/10.jpg?src=../../etc",
        "/overlay/DoE3_19/10.jpg?cls=xyz",
        "/overlay/DoE3_19/10.jpg?a=500",
        "/overlay/..%2Fmeta/10.jpg",
    ],
)
def test_overlay_rejects_bad_params(client, path):
    assert client.get(path).status_code in (400, 404)


def test_valid_run_whitelist():
    assert data.valid_run("DoE3_19") == "DoE3_19"
    for bad in ["DoE3_28", "DoE4_1", "../DoE3_19", "DoE3_19/../x", None, 42, "doe3_19"]:
        assert data.valid_run(bad) is None


def test_process_payload_shapes():
    from weldmon.app.tabs import process

    payload = process.live_payload("DoE3_19", "dark")
    n = payload["n"]
    assert all(len(v) == n for v in payload["ts"].values())
    assert payload["next"] in data.runs_by_id()
    assert {e["type"] for e in payload["events"]} >= {"on", "off"}


def test_run_verdicts_follow_quality_rules():
    q = data.meta()["quality"]
    for r in data.runs():
        assert r["verdict"] in ("ok", "warn", "nok")
        if r["n_speed_deviation"] or r["n_alarms"] > q["verdict_warn_max_alarms"]:
            assert r["verdict"] == "nok"
        elif r["n_alarms"] <= q["verdict_ok_max_alarms"]:
            assert r["verdict"] == "ok"
        else:
            assert r["verdict"] == "warn"
    assert 0 < q["stability_limit_cv"] < 2


def test_history_orders_campaigns_newest_first():
    from weldmon.app.tabs import history

    runs = history.runs_sorted()
    assert [r["serie"] for r in runs[:1]] == ["DoE3"] and runs[-1]["serie"] == "DoE1"
    doe3 = [r["point"] for r in runs if r["serie"] == "DoE3"]
    assert doe3 == sorted(doe3)
    fig = history.trend_figure("DoE3_19", "nok", "dark")
    assert len(fig["data"][0]["x"]) == len(data.runs())


def test_history_detail_renders_every_run():
    from weldmon.app.tabs import history

    for r in data.runs():
        assert history.detail(r)
