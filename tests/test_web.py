from __future__ import annotations


def test_main_pages_render(admin):
    client, _ = admin
    for path in [
        "/",
        "/clients",
        "/deals",
        "/tasks",
        "/payments",
        "/warehouse",
        "/accounting",
        "/reports",
        "/admin/users",
        "/admin/projects",
        "/admin/activity",
        "/admin/settings",
        "/profile",
    ]:
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.status_code}"
        assert "Custom-CRM" in response.text


def test_web_client_form_and_search(admin):
    client, token = admin
    response = client.post(
        "/clients/new",
        data={
            "_csrf": token,
            "name": "Веб-клиент",
            "company": "ООО Веб",
            "email": "web@example.com",
            "phone": "",
            "status": "new",
            "source": "Сайт",
            "notes": "",
            "owner_id": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/clients/")
    detail = client.get(location)
    assert detail.status_code == 200
    assert "Веб-клиент" in detail.text

    search = client.get("/search?q=веб-клиент")
    assert search.status_code == 200
    assert "Веб-клиент" in search.text


def test_web_csrf_rejected(admin):
    client, _ = admin
    response = client.post(
        "/clients/new",
        data={"name": "Без токена"},
        follow_redirects=False,
    )
    assert response.status_code == 403
