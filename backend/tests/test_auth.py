"""Coach workspace sign-in and API guards."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth
from app.config import settings
from app.routes import auth as auth_routes
from app.routes import labelling as labelling_routes
from tests.test_labelling_clips import seed_analysis

ADMIN_PW = "admin-secret"
COACH_PW = "coach-secret"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "admin_password", ADMIN_PW)
    monkeypatch.setattr(settings, "coach_password", COACH_PW)
    monkeypatch.setattr(settings, "session_secret", "test-secret")
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    seed_analysis(tmp_path, "a1")
    app = FastAPI()
    app.include_router(auth_routes.router)
    app.include_router(labelling_routes.router)
    return TestClient(app)


def _login(client: TestClient, password: str) -> None:
    res = client.post("/auth/login", json={"password": password})
    assert res.status_code == 200, res.text


def test_token_round_trip_and_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "session_secret", "s1")
    token = auth.create_token("coach", now=1000)
    session = auth.read_token(token, now=1001)
    assert session is not None and session.role == "coach" and session.name == settings.coach_name
    payload, sig = token.split(".")
    assert auth.read_token(f"{payload}.{sig[:-2]}xx", now=1001) is None
    forged = auth._b64(b'{"role":"admin","exp":99999999999}')
    assert auth.read_token(f"{forged}.{sig}", now=1001) is None
    assert auth.read_token(token, now=1000 + settings.session_max_age_hours * 3600 + 1) is None
    monkeypatch.setattr(settings, "session_secret", "other")
    assert auth.read_token(token, now=1001) is None


def test_passwords_map_to_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_password", ADMIN_PW)
    monkeypatch.setattr(settings, "coach_password", COACH_PW)
    assert auth.role_for_password(ADMIN_PW) == "admin"
    assert auth.role_for_password(COACH_PW) == "coach"
    assert auth.role_for_password("nope") is None
    monkeypatch.setattr(settings, "coach_password", "")
    assert auth.role_for_password("") is None


def test_login_sets_an_httponly_cookie_and_me_reports_the_role(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json={"password": "wrong"}).status_code == 401
    res = client.post("/auth/login", json={"password": COACH_PW})
    assert res.json() == {"role": "coach", "name": "Jeff"}
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("bl_session=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/auth/me").json() == {"role": "coach", "name": "Jeff"}
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_labelling_api_needs_a_session(client: TestClient) -> None:
    for path in ("/labelling/datasets", "/labelling/datasets/x", "/labelling/clips/a1", "/labelling/clips/a1/pose"):
        assert client.get(path).status_code == 401, path
    assert client.put("/labelling/clips/a1/label", json={}).status_code == 401
    _login(client, COACH_PW)
    assert client.get("/labelling/clips/a1").status_code == 200


def test_coach_cannot_use_admin_endpoints(client: TestClient) -> None:
    _login(client, COACH_PW)
    assert client.get("/labelling/jobs/abc").status_code == 403
    assert client.get("/labelling/datasets/x/export").status_code == 403
    assert client.get("/labelling/analyses", params={"technique": "FOREHAND_CLEAR"}).status_code == 403
    assert client.patch("/labelling/datasets/x", json={"due_date": "2030-01-01"}).status_code == 403
    res = client.post(
        "/labelling/datasets",
        data={"technique": "FOREHAND_CLEAR", "due_date": "2030-01-01"},
        files=[("files", ("a.mp4", b"x", "video/mp4"))],
    )
    assert res.status_code == 403


def test_only_the_coach_labels_and_always_as_jeff(client: TestClient) -> None:
    _login(client, ADMIN_PW)
    assert client.put("/labelling/clips/a1/label", json={"overall_rating": 3}).status_code == 403
    client.post("/auth/logout")

    _login(client, COACH_PW)
    res = client.put(
        "/labelling/clips/a1/label", json={"coach": "Somebody else", "overall_rating": 3}
    )
    assert res.status_code == 200
    assert res.json()["label"]["coach"] == "Jeff"
    mine = client.get("/labelling/clips/a1/label", params={"coach": "Somebody else"}).json()
    assert mine["label"]["coach"] == "Jeff"


def test_admin_reads_any_coachs_label_read_only(client: TestClient) -> None:
    from app.labelling.labels import LabelStore

    LabelStore().write({"analysis_id": "a1", "coach": "Linh", "overall_rating": 2, "stats": {}})
    _login(client, ADMIN_PW)
    old = client.get("/labelling/clips/a1/label", params={"coach": "Linh"}).json()
    assert old["label"]["overall_rating"] == 2
    assert client.get("/labelling/clips/a1/label").json()["label"] is None  # Jeff's: none yet
