from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.github import client as github_client
from apps.github import oauth
from apps.repos.models import Installation, InstallationMember, Repository
from tests.conftest import post_webhook


def test_webhook_rejects_bad_signature_and_missing_headers(client, db):
    assert post_webhook(client, "ping", {}, signature="sha256=bad").status_code == 401
    assert post_webhook(client, "ping", {}, signature="").status_code == 401
    ok = post_webhook(client, "ping", {"zen": "hi"})
    assert ok.status_code == 202 and ok.json()["status"] == "pong"


def test_installation_created_and_deleted(client, db, monkeypatch):
    monkeypatch.setattr(
        github_client,
        "list_installation_repositories",
        lambda _id: [
            {"id": 5, "full_name": "acme/web", "private": True, "default_branch": "trunk"}
        ],
    )
    payload = {
        "action": "created",
        "installation": {"id": 77, "account": {"login": "acme", "type": "Organization"}},
        "repositories": [{"id": 5, "full_name": "acme/web", "private": True}],
    }
    assert post_webhook(client, "installation", payload, "i-1").status_code == 202
    repo = Repository.objects.get(github_repo_id=5)
    assert repo.default_branch == "trunk" and repo.is_private
    assert repo.installation.account_login == "acme"

    deleted = {"action": "deleted", "installation": {"id": 77, "account": {"login": "acme"}}}
    post_webhook(client, "installation", deleted, "i-2")
    assert not Installation.objects.filter(github_installation_id=77).exists()
    assert not Repository.objects.filter(github_repo_id=5).exists()


def test_repositories_added_and_removed(client, installation, repo, monkeypatch):
    monkeypatch.setattr(github_client, "list_installation_repositories", lambda _id: [])
    payload = {
        "action": "added",
        "installation": {"id": installation.github_installation_id, "account": {"login": "acme"}},
        "repositories_added": [{"id": 8, "full_name": "acme/new", "private": False}],
        "repositories_removed": [{"id": repo.github_repo_id, "full_name": repo.full_name}],
    }
    post_webhook(client, "installation_repositories", payload, "r-1")
    assert Repository.objects.filter(github_repo_id=8).exists()
    assert not Repository.objects.filter(github_repo_id=repo.github_repo_id).exists()


def test_install_button_redirects_to_github_with_state(client, db):
    response = client.get("/api/github/install")
    assert response.status_code == 302
    assert response["Location"].startswith(
        "https://github.com/apps/aethos/installations/new?state="
    )
    assert client.session["install_state"] in response["Location"]


@pytest.fixture
def oauth_stubs(monkeypatch):
    monkeypatch.setattr(oauth, "exchange_code", lambda code: "user-token")
    monkeypatch.setattr(oauth, "fetch_user", lambda token: oauth.GitHubUser(10, "octo", "http://a"))
    monkeypatch.setattr(
        oauth,
        "fetch_user_installations",
        lambda token: [oauth.InstallationInfo(111, "acme", "Organization")],
    )
    monkeypatch.setattr(
        github_client,
        "list_installation_repositories",
        lambda _id: [
            {"id": 222, "full_name": "acme/app", "private": False, "default_branch": "main"}
        ],
    )


def test_setup_callback_logs_in_and_links_installation(client, db, oauth_stubs):
    client.get("/api/github/install")
    state = client.session["install_state"]
    response = client.get(
        "/api/github/setup", {"code": "abc", "state": state, "installation_id": 111}
    )
    assert response.status_code == 302 and response["Location"].endswith("/app")
    user = User.objects.get(github_user_id=10)
    assert InstallationMember.objects.filter(
        user=user, installation__github_installation_id=111
    ).exists()
    assert Repository.objects.filter(full_name="acme/app").exists()
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["login"] == "octo" and me.json()["csrf_token"]


def test_setup_callback_with_bad_state_goes_through_login(client, db, oauth_stubs):
    client.get("/api/github/install")
    response = client.get("/api/github/setup", {"code": "abc", "state": "wrong"})
    assert response["Location"] == "/api/auth/login"
    assert client.get("/api/auth/me").status_code == 401


def test_login_flow_requires_matching_state(client, db, oauth_stubs):
    login = client.get("/api/auth/login")
    assert login.status_code == 302 and "github.com/login/oauth/authorize" in login["Location"]
    state = client.session["oauth_state"]
    bad = client.get("/api/auth/callback", {"code": "x", "state": "nope"})
    assert "error=login_failed" in bad["Location"]
    client.get("/api/auth/login")
    good = client.get("/api/auth/callback", {"code": "x", "state": client.session["oauth_state"]})
    assert good["Location"].endswith("/app")
    assert state != client.session.get("oauth_state")


def test_membership_is_replaced_on_login(client, db, oauth_stubs, user, installation):
    stale = Installation.objects.create(github_installation_id=555, account_login="gone")
    InstallationMember.objects.create(user=user, installation=stale)
    user.github_user_id = 10
    user.save()
    client.get("/api/auth/login")
    client.get("/api/auth/callback", {"code": "x", "state": client.session["oauth_state"]})
    ids = set(
        InstallationMember.objects.filter(user=user).values_list(
            "installation__github_installation_id", flat=True
        )
    )
    assert ids == {111}


def test_logout_requires_csrf_and_clears_session(client, user):
    client.force_login(user)
    csrf_client = type(client)(enforce_csrf_checks=True)
    csrf_client.force_login(user)
    token = csrf_client.get("/api/auth/me").json()["csrf_token"]
    assert csrf_client.post("/api/auth/logout").status_code == 403
    ok = csrf_client.post("/api/auth/logout", HTTP_X_CSRFTOKEN=token)
    assert ok.status_code == 200
    assert csrf_client.get("/api/auth/me").status_code == 401
