from __future__ import annotations

from httpx import AsyncClient


async def authenticate_test_client(
    client: AsyncClient,
    *,
    email: str = "test-user@example.com",
    organization_name: str = "Test Workspace",
) -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "secure-password",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    client.headers.update({"Authorization": f"Bearer {payload['access_token']}"})
    return payload
