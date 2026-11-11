def register(client, email="dev@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Dev User",
            "password": "A-strong-password-123",
        },
    )
    assert response.status_code == 201
    return response.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_profile_and_refresh_rotation(client):
    tokens = register(client)
    assert (
        client.get("/api/v1/auth/me", headers=auth(tokens["access_token"])).json()["email"]
        == "dev@example.com"
    )
    assert (
        client.patch(
            "/api/v1/auth/me",
            headers=auth(tokens["access_token"]),
            json={"full_name": "Updated Dev"},
        ).json()["full_name"]
        == "Updated Dev"
    )
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200 and rotated.json()["refresh_token"] != tokens["refresh_token"]
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "dev@example.com", "password": "A-strong-password-123"},
        ).status_code
        == 200
    )


def test_duplicate_registration_and_invalid_login(client):
    register(client)
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "DEV@example.com",
                "full_name": "Other",
                "password": "A-strong-password-123",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "dev@example.com", "password": "wrong"}
        ).status_code
        == 401
    )


def test_project_crud_is_owner_scoped(client):
    first, second = register(client), register(client, "other@example.com")
    h1, h2 = auth(first["access_token"]), auth(second["access_token"])
    created = client.post(
        "/api/v1/projects",
        headers=h1,
        json={"name": "Core", "description": "Main repo"},
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    assert len(client.get("/api/v1/projects", headers=h1).json()) == 1
    assert client.get("/api/v1/projects", headers=h2).json() == []
    assert client.get(f"/api/v1/projects/{pid}", headers=h2).status_code == 404
    assert (
        client.patch(f"/api/v1/projects/{pid}", headers=h1, json={"name": "Core 2"}).json()["name"]
        == "Core 2"
    )
    assert client.delete(f"/api/v1/projects/{pid}", headers=h1).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=h1).status_code == 404


def test_protected_routes_require_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects").status_code == 401
