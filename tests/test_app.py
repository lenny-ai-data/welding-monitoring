"""Tests HTTP de l'app (sécurité, routes média, liste blanche). Nécessitent app_data/ généré."""

import pytest

from weldmon.app import data

# Préparation : sautés sans app_data/ (CI) ---------------------------------------------------------
pytestmark = pytest.mark.skipif(not (data.DATA_DIR / "runs.json").exists(), reason="app_data/ absent")


@pytest.fixture(scope="module")
def client():
    from weldmon.app import create_app

    return create_app().server.test_client()


# En-têtes de sécurité -----------------------------------------------------------------------------


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


# Routes et médias ---------------------------------------------------------------------------------


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


def test_segmentation_files_served(client):
    for path in ("frames/060.webp", "gt/060.png", "pred/060.png"):
        r = client.get(f"/media/seg/DoE3_19/{path}")
        assert r.status_code == 200
        assert "max-age" in r.headers["Cache-Control"]


# Listes blanches ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/media/runs.json",
        "/media/../runs.json",
        "/media/%2e%2e/meta.json",
        "/media/videos/../../meta.json",
        "/media/videos/DoE9_1.mp4",
        "/media/videos/DoE3_99.mp4",
        "/media/seg/DoE3_19/gt/000.webp",
        "/media/seg/DoE3_19/../../meta.json",
        "/media/seg/DoE3_19/gt/9999.png",
        "/media/seg/DoE1_1/gt/000.png",  # run non annoté : fichier absent
    ],
)
def test_media_whitelist(client, path):
    assert client.get(path).status_code == 404


def test_valid_run_whitelist():
    assert data.valid_run("DoE3_19") == "DoE3_19"
    for bad in ["DoE3_28", "DoE4_1", "../DoE3_19", "DoE3_19/../x", None, 42, "doe3_19"]:
        assert data.valid_run(bad) is None


# Données exportées et rendu des onglets -----------------------------------------------------------


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


def test_doe_factor_constants_match_data():
    from weldmon.app.tabs import doe

    assert list(doe.FACTORS) == list(data.doe()["factors"])


def all_layouts():
    """Mises en page de tous les graphes de l'app, pour un run et un indicateur représentatifs."""
    from weldmon.app.tabs import doe, history, process, segmentation

    kpi = next(iter(data.doe()["kpis"]))
    yield from process.live_payload("DoE3_19", "dark")["layouts"].values()
    yield history.trend_figure("DoE3_19", "all", "dark")["layout"]
    yield doe.surface_fig(kpi, "P", "v", "dark")["layout"]
    yield doe.pareto_fig(kpi, "dark")["layout"]
    yield from (f["layout"] for f in doe.main_effects(kpi, "dark").values())
    yield doe.spc_fig(kpi, "dark")["layout"]
    figs = segmentation.area_figs("DoE3_19", "dark")
    yield figs["areas"]["layout"]
    yield figs["iou"]["layout"]


def test_figures_cannot_be_zoomed():
    layouts = list(all_layouts())
    assert len(layouts) >= 12
    for layout in layouts:
        assert layout.get("dragmode") is False
        axes = [k for k in layout if k.startswith(("xaxis", "yaxis"))]
        assert axes and all(layout[k].get("fixedrange") is True for k in axes), axes
