import uuid

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.main import app
from app.models import User, UserRole


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("role", "path"),
    [
        (UserRole.USER, "/api/v1/owner/dashboard"),
        (UserRole.STAFF, "/api/v1/owner/dashboard"),
        (UserRole.USER, "/api/v1/staff/dashboard"),
        (UserRole.OWNER, "/api/v1/staff/dashboard"),
        (UserRole.USER, "/api/v1/admin/dashboard"),
        (UserRole.STAFF, "/api/v1/admin/dashboard"),
        (UserRole.OWNER, "/api/v1/admin/dashboard"),
    ],
)
def test_role_dashboard_rejects_other_roles(role: UserRole, path: str) -> None:
    actor = User(id=uuid.uuid4(), email="role-test@example.com", username="role-test", full_name="Role Test", password_hash="unused", role=role, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: actor

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 403


def test_role_dashboard_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/dashboard")

    assert response.status_code == 401