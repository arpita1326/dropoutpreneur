import re
import sqlite3

import pytest

from app import PATHS, app, init_db, lessons_for


@pytest.fixture()
def client(tmp_path):
    database = tmp_path / "test.db"
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True, DATABASE=str(database), SECRET_KEY="test-secret")
    with app.app_context():
        init_db()
    with app.test_client() as test_client:
        yield test_client


def token(client, path):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match, f"Missing CSRF token in {path}"
    return match.group(1).decode()


def register(client, email="user@example.com", name="Test User"):
    csrf = token(client, "/register")
    response = client.post("/register", data={"csrf_token": csrf, "name": name, "email": email, "password": "password123", "confirm": "password123"})
    assert response.status_code == 302
    return response


def login(client, email="user@example.com"):
    csrf = token(client, "/login")
    return client.post("/login", data={"csrf_token": csrf, "email": email, "password": "password123"})


def test_authentication_and_csrf(client):
    assert client.get("/dashboard").status_code == 302
    assert client.post("/register", data={"name": "No Token", "email": "x@example.com", "password": "password123", "confirm": "password123"}).status_code == 400
    register(client)
    assert client.post("/register", data={"csrf_token": token(client, "/register"), "name": "Test User", "email": "user@example.com", "password": "password123", "confirm": "password123"}).status_code == 200
    client.get("/logout")
    assert login(client).status_code == 302
    client.get("/logout")
    assert login(client, "user@example.com").status_code == 302
    csrf = token(client, "/login")
    assert client.post("/login", data={"csrf_token": csrf, "email": "user@example.com", "password": "wrong-password"}).status_code == 200


def test_all_paths_and_progress(client):
    register(client)
    for path_key in PATHS:
        assert client.get(f"/learning/{path_key}").status_code == 200
        lessons = lessons_for(path_key)
        first_token = token(client, f"/learning/{path_key}/lesson/0")
        response = client.post(f"/learning/{path_key}/lesson/0", data={"csrf_token": first_token})
        assert response.status_code == 302
        assert client.get(f"/learning/{path_key}/lesson/0").status_code == 200
        assert client.get(f"/learning/{path_key}/lesson/{len(lessons)}").status_code == 404


def test_completion_is_unique_and_reaches_100_percent(client):
    register(client)
    total = len(lessons_for("python"))
    for index in range(total):
        csrf = token(client, f"/learning/python/lesson/{index}")
        assert client.post(f"/learning/python/lesson/{index}", data={"csrf_token": csrf}, follow_redirects=True).status_code == 200
    response = client.get("/learning/python")
    assert b"100%" in response.data
    csrf = token(client, "/learning/python/lesson/0")
    client.post("/learning/python/lesson/0", data={"csrf_token": csrf})
    with app.app_context():
        count = sqlite3.connect(app.config["DATABASE"]).execute("SELECT COUNT(*) FROM progress").fetchone()[0]
    assert count == total


def test_user_isolation_for_progress_and_career(client):
    register(client, "a@example.com", "User A")
    csrf = token(client, "/learning/python/lesson/0")
    client.post("/learning/python/lesson/0", data={"csrf_token": csrf})
    career_csrf = token(client, "/career")
    client.post("/career", data={"csrf_token": career_csrf, "enjoy": "ai", "work": "ai", "level": "beginner", "build": "ai"})
    client.get("/logout")

    register(client, "b@example.com", "User B")
    assert b"0%" in client.get("/learning/python").data
    assert b"AI / ML Engineer" not in client.get("/career/result").data
    profile_csrf = token(client, "/profile")
    client.post("/profile", data={"csrf_token": profile_csrf, "name": "Changed B", "career_goal": "Testing"})
    client.get("/logout")
    login(client, "a@example.com")
    assert b"User A" in client.get("/profile").data
    assert b"Changed B" not in client.get("/profile").data
    assert b"6%" in client.get("/learning/python").data


def test_career_result_and_error_routes(client):
    register(client)
    csrf = token(client, "/career")
    response = client.post("/career", data={"csrf_token": csrf, "enjoy": "coding", "work": "coding", "level": "beginner", "build": "web"})
    assert response.status_code == 302
    assert b"Software Developer" in client.get("/career/result").data
    assert client.get("/learning/unknown").status_code == 404
    assert client.get("/learning/python/lesson/999").status_code == 404
    assert client.post("/career", data={"enjoy": "ai"}).status_code == 400
