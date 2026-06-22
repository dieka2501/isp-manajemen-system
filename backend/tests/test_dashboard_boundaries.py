from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.api.client_dashboard import (
    AgentPreviewRequest,
    LearningMapRequest,
    approve_registration,
    map_learning_unprocessed,
    registrations,
    summary,
)
from app.api.registrations import (
    InstallationCompleteRequest,
    RegistrationApproveRequest,
    RegistrationPaymentRequest,
)
from app.auth.guards import dashboard_destination, require_client, require_provider
from app.client_dashboard.permissions import ClientPermission
from app.client_dashboard.routes import _client_page, legacy_client_dashboard
from app.core.config import Settings
from app.main import app
from app.provider_dashboard.permissions import ProviderPermission
from app.provider_dashboard.routes import _provider_page, legacy_provider_dashboard
from app.services.client_dashboard_auth import ClientDashboardTokenService
from app.services.dashboard_auth import DashboardAuthService
from app.services.dashboard_auth import DashboardAuthState


class DashboardBoundaryTests(unittest.TestCase):
    def _settings(self, temp_dir: str) -> Settings:
        return Settings(
            chat_database_path=str(Path(temp_dir) / "dashboard-boundaries.sqlite3"),
            billing_sample_xlsx_path="",
            dashboard_secret="provider-test-secret",
            dashboard_cookie_name="provider_test_session",
            client_dashboard_jwt_secret="client-test-secret",
            client_dashboard_cookie_name="client_test_session",
            client_dashboard_seed_email="admin@isp.local",
            client_dashboard_seed_password="password",
        )

    def _request(self, cookies: dict[str, str] | None = None) -> Request:
        headers: list[tuple[bytes, bytes]] = []
        if cookies:
            value = "; ".join(f"{key}={token}" for key, token in cookies.items())
            headers.append((b"cookie", value.encode("ascii")))
        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
            }
        )

    def _provider_cookie(self, settings: Settings) -> str:
        return DashboardAuthService(settings)._encode_token(int(time.time()) + 3600)

    def _client_cookie(self, settings: Settings, client_id: int = 1) -> str:
        return ClientDashboardTokenService(settings).issue_token(client_id)[0]

    def _invalid_actor_client_cookie(self, settings: Settings) -> str:
        service = ClientDashboardTokenService(settings)
        now = int(time.time())
        signing_input = ".".join(
            [
                service._encode_json({"alg": "HS256", "typ": "JWT"}),
                service._encode_json(
                    {
                        "actor": "subscriber",
                        "sub": "1",
                        "iat": now,
                        "exp": now + 3600,
                        "permissions": [],
                    }
                ),
            ]
        )
        return f"{signing_input}.{service._sign(signing_input)}"

    def test_root_redirect_is_actor_aware_and_rejects_ambiguous_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            provider_cookie = self._provider_cookie(settings)
            client_cookie = self._client_cookie(settings)

            with patch("app.auth.guards.get_settings", return_value=settings):
                self.assertEqual(dashboard_destination(self._request()), "/login")
                self.assertEqual(
                    dashboard_destination(
                        self._request({settings.dashboard_cookie_name: provider_cookie})
                    ),
                    "/sqlexplore",
                )
                self.assertEqual(
                    dashboard_destination(
                        self._request({settings.client_dashboard_cookie_name: client_cookie})
                    ),
                    "/client-dashboard",
                )
                self.assertEqual(
                    dashboard_destination(
                        self._request(
                            {
                                settings.dashboard_cookie_name: provider_cookie,
                                settings.client_dashboard_cookie_name: client_cookie,
                            }
                        )
                    ),
                    "/unauthorized",
                )

                invalid_actor = DashboardAuthState(
                    authenticated=True,
                    secret_configured=True,
                    expires_at=int(time.time()) + 3600,
                    actor="subscriber",
                    permissions=(),
                )
                with patch.object(
                    DashboardAuthService,
                    "status",
                    return_value=invalid_actor,
                ):
                    self.assertEqual(
                        dashboard_destination(self._request()),
                        "/unauthorized",
                    )

                self.assertEqual(
                    dashboard_destination(
                        self._request(
                            {
                                settings.client_dashboard_cookie_name: self._invalid_actor_client_cookie(
                                    settings
                                )
                            }
                        )
                    ),
                    "/unauthorized",
                )

    def test_provider_and_client_page_guards_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            provider_request = self._request(
                {settings.dashboard_cookie_name: self._provider_cookie(settings)}
            )
            client_request = self._request(
                {
                    settings.client_dashboard_cookie_name: self._client_cookie(settings)
                }
            )

            with patch("app.auth.guards.get_settings", return_value=settings):
                client_to_provider = _provider_page(client_request)
                provider_to_client = _client_page(provider_request)
                anonymous_provider = _provider_page(self._request())
                anonymous_client = _client_page(self._request())

            self.assertIsInstance(client_to_provider, RedirectResponse)
            self.assertEqual(client_to_provider.headers["location"], "/unauthorized")
            self.assertEqual(provider_to_client.headers["location"], "/unauthorized")
            self.assertEqual(anonymous_provider.headers["location"], "/login/provider")
            self.assertEqual(anonymous_client.headers["location"], "/login/client")

    def test_api_guards_forbid_cross_dashboard_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            provider_request = self._request(
                {settings.dashboard_cookie_name: self._provider_cookie(settings)}
            )
            client_request = self._request(
                {settings.client_dashboard_cookie_name: self._client_cookie(settings)}
            )
            invalid_actor_request = self._request(
                {
                    settings.client_dashboard_cookie_name: self._invalid_actor_client_cookie(
                        settings
                    )
                }
            )

            with patch("app.auth.guards.get_settings", return_value=settings):
                provider_session = require_provider(
                    provider_request,
                    ProviderPermission.DASHBOARD_ACCESS,
                )
                client_session = require_client(
                    client_request,
                    permission=ClientPermission.DASHBOARD_ACCESS,
                )
                with self.assertRaises(HTTPException) as client_provider_error:
                    require_provider(client_request, ProviderPermission.DASHBOARD_ACCESS)
                with self.assertRaises(HTTPException) as provider_client_error:
                    require_client(
                        provider_request,
                        permission=ClientPermission.DASHBOARD_ACCESS,
                    )
                with self.assertRaises(HTTPException) as invalid_client_error:
                    require_client(
                        invalid_actor_request,
                        permission=ClientPermission.DASHBOARD_ACCESS,
                    )

                limited_provider = DashboardAuthState(
                    authenticated=True,
                    secret_configured=True,
                    expires_at=int(time.time()) + 3600,
                    actor="provider",
                    permissions=(ProviderPermission.DASHBOARD_ACCESS.value,),
                )
                with patch.object(
                    DashboardAuthService,
                    "status",
                    return_value=limited_provider,
                ):
                    with self.assertRaises(HTTPException) as permission_error:
                        require_provider(
                            provider_request,
                            ProviderPermission.SQLITE_MANAGE,
                        )

            self.assertEqual(client_provider_error.exception.status_code, 403)
            self.assertEqual(provider_client_error.exception.status_code, 403)
            self.assertEqual(invalid_client_error.exception.status_code, 403)
            self.assertEqual(permission_error.exception.status_code, 403)
            self.assertEqual(provider_session.actor, "provider")
            self.assertEqual(client_session.client_id, 1)

    def test_provider_auth_is_not_implicitly_enabled_without_secret(self) -> None:
        service = DashboardAuthService(Settings(dashboard_secret=""))

        self.assertFalse(service.status(self._request()).authenticated)
        with self.assertRaises(HTTPException) as error:
            service.login("any-password", Response())

        self.assertEqual(error.exception.status_code, 503)

    def test_cross_tenant_learning_resource_is_not_mutated(self) -> None:
        store = Mock()
        store.get_unprocessed_question.return_value = {"id": 99, "client_id": 2}
        payload = LearningMapRequest(
            intent_code="ask_price",
            mapping_type="sample",
            keyword=None,
            normalized_keyword=None,
            weight=4,
            notes=None,
        )

        with patch("app.api.client_dashboard._store", return_value=store):
            with self.assertRaises(HTTPException) as error:
                map_learning_unprocessed(99, payload, client={"id": 1})

        self.assertEqual(error.exception.status_code, 404)
        store.map_unprocessed_question.assert_not_called()

    def test_client_id_body_is_rejected_and_query_scope_uses_session_client(self) -> None:
        with self.assertRaises(ValidationError):
            AgentPreviewRequest.model_validate(
                {"message": "test", "client_id": 999999}
            )
        with self.assertRaises(ValidationError):
            RegistrationApproveRequest.model_validate(
                {"amount": 100000, "client_id": 999999}
            )
        with self.assertRaises(ValidationError):
            RegistrationPaymentRequest.model_validate(
                {
                    "payment_method": "cash",
                    "amount": 100000,
                    "client_id": 999999,
                }
            )
        with self.assertRaises(ValidationError):
            InstallationCompleteRequest.model_validate(
                {"notes": "done", "client_id": 999999}
            )

        store = Mock()
        store.get_client_dashboard_summary.return_value = {"total_customers": 0}
        with patch("app.api.client_dashboard._store", return_value=store):
            result = summary(client={"id": 7})

        self.assertEqual(result["item"]["total_customers"], 0)
        store.get_client_dashboard_summary.assert_called_once_with(7)

    def test_registration_workflow_uses_authenticated_client_scope(self) -> None:
        store = Mock()
        store.list_customer_registrations.return_value = []
        store.approve_customer_registration.return_value = {
            "id": 91,
            "status": "approved",
        }

        with (
            patch("app.api.client_dashboard._store", return_value=store),
            patch(
                "app.api.client_dashboard._send_customer_message",
                return_value={"sent": False},
            ),
        ):
            listed = registrations(
                status_filter="registered",
                limit=25,
                client={"id": 7},
            )
            approved = approve_registration(
                91,
                RegistrationApproveRequest(amount=100000),
                client={"id": 7},
            )

        self.assertEqual(listed, {"items": []})
        self.assertEqual(approved["item"]["status"], "approved")
        store.list_customer_registrations.assert_called_once_with(
            status_filter="registered",
            limit=25,
            client_id=7,
        )
        store.approve_customer_registration.assert_called_once_with(
            registration_id=91,
            amount=100000,
            payment_method="virtual_account",
            virtual_account=None,
            notes=None,
            client_id=7,
        )

    def test_canonical_and_legacy_routes_are_registered_without_old_provider_api(self) -> None:
        paths = {getattr(route, "path", "") for route in app.routes}

        self.assertIn("/sqlexplore", paths)
        self.assertIn("/sqlexplore/{dashboard_path:path}", paths)
        self.assertIn("/client-dashboard", paths)
        self.assertIn("/client-dashboard/{dashboard_path:path}", paths)
        self.assertIn("/api/v1/provider/sqlite/sources", paths)
        self.assertIn("/api/v1/provider/message-dumps/items", paths)
        self.assertIn("/api/v1/client/summary", paths)
        self.assertIn("/api/v1/client/registrations/items", paths)
        self.assertIn("/api/v1/client/registrations/{registration_id}/approve", paths)
        self.assertNotIn("/api/v1/provider/registrations/items", paths)
        self.assertNotIn("/api/v1/provider/registrations/{registration_id}/approve", paths)
        self.assertNotIn("/api/v1/provider/registrations/message-dumps", paths)
        self.assertNotIn("/api/v1/sqlite/sources", paths)
        self.assertNotIn("/api/v1/chat/clients", paths)

        self.assertEqual(legacy_client_dashboard().headers["location"], "/client-dashboard")
        self.assertEqual(legacy_provider_dashboard().headers["location"], "/sqlexplore")


if __name__ == "__main__":
    unittest.main()
