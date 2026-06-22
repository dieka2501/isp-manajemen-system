# Provider and Client Dashboard Separation

Implemented: 2026-06-22

## Canonical product surfaces

| Surface | Canonical page namespace | Canonical API namespace | Actor |
| --- | --- | --- | --- |
| Provider Dashboard | `/sqlexplore/*` | `/api/v1/provider/*` | Internal Provider User |
| Client Dashboard | `/client-dashboard/*` | `/api/v1/client/*` | Authenticated Client User |
| Authentication | `/login`, `/login/provider`, `/login/client` | Provider/Client auth endpoints | Public until authenticated |
| Subscriber registration/payment | `/register/{token}`, `/payment/{token}` | `/api/v1/registrations/public/*` | Public token holder |

`/` contains no dashboard implementation. It resolves the signed server-visible session and redirects to the matching product surface, `/login`, or `/unauthorized`.

## Module boundaries

```text
backend/app/
  auth/
    guards.py
    roles.py
    routes.py
  provider_dashboard/
    api.py
    permissions.py
    routes.py
  client_dashboard/
    api.py
    permissions.py
    routes.py

frontend/
  provider-dashboard/
    layouts/
    navigation/
    permissions/
    routes/
  client-dashboard/
    layouts/
    navigation/
    permissions/
    routes/
```

The existing large page controllers remain dashboard-owned entry scripts. Their layout, navigation, route map, permission names, and API namespaces are now separate; no combined navigation array is filtered in the browser.

## Authentication and authorization

- Provider sessions are signed HttpOnly cookies with an explicit `provider` actor claim and named Provider permissions.
- Client sessions are signed HttpOnly cookies with an explicit `client` actor claim, the authenticated client ID in `sub`, and named Client permissions.
- Bearer Client tokens remain accepted temporarily for API compatibility, but the frontend no longer stores the token in `localStorage`.
- A Provider session cannot call Client API routes or open Client pages.
- A Client session cannot call Provider API routes or open Provider pages.
- Ambiguous sessions containing both actor cookies resolve to `/unauthorized`; each successful login also deletes the other actor cookie.
- Provider authentication no longer becomes implicitly authenticated when `DASHBOARD_SECRET` is empty. Provider login returns a configuration error until a secret is configured.

## Tenant isolation

Client API dependencies derive the tenant exclusively from the signed session:

```text
authenticated_client_id = signed_session.sub
```

Tenant-scoped store calls receive this ID. Device selection is verified against the authenticated client's device list, and learning-resource mutation checks resource ownership before writing. Registration listing, approval, payment confirmation, and activation all pass the session client ID into the store lookup; a registration owned by another Client resolves as not found before mutation. Unknown request-body properties are rejected, so an injected `client_id` cannot influence Client operations. Query-string `client_id` values are not API inputs and are ignored; the session tenant remains authoritative.

## Registration approval ownership correction

The registration approval workflow is owned by the ISP Client, not the platform Provider:

| Concern | Canonical location |
| --- | --- |
| Page and navigation | `/client-dashboard/registrations` in `clientNavigation` |
| Permission | `client.registrations.manage` |
| List | `GET /api/v1/client/registrations/items` |
| Approve | `POST /api/v1/client/registrations/{id}/approve` |
| Record payment | `POST /api/v1/client/registrations/{id}/payment` |
| Activate after installation | `POST /api/v1/client/registrations/{id}/activate` |

The Provider navigation and Provider approval endpoints were removed. Provider-owned Message Dumps use their own `/api/v1/provider/message-dumps*` boundary. Subscriber registration/payment pages and the validated virtual-account callback remain shared public/integration surfaces.

Cross-tenant operations that previously lived on unauthenticated `/api/v1/chat/*` routes now live under the Provider namespace and require explicit Provider permissions.

## Compatibility and deprecation

| Legacy route | Migration behavior |
| --- | --- |
| `/dashboard` and `/dashboard/*` | Permanent redirect to `/client-dashboard` and matching suffix |
| `/sqlexplorer` and `/sqlexplorer/*` | Permanent redirect to `/sqlexplore` and matching suffix |
| `/api/v1/client-dashboard/*` | Temporary deprecated alias to the same guarded Client handlers |
| `/api/v1/sqlite/*` | Removed; use `/api/v1/provider/sqlite/*` |
| `/api/v1/chat/*` | Removed; use `/api/v1/provider/chat/*` |
| `/api/v1/registrations/admin/{registration workflow}` | Removed; use tenant-scoped `/api/v1/client/registrations/*` |

The legacy Client API alias does not duplicate implementation; FastAPI mounts the same guarded Client router under the old prefix for the migration window.

Dashboard HTML files are not served by static-asset mounts. Static mounts use allowlists for each dashboard, preventing a user from bypassing page guards through an asset URL.

## Verification coverage

`backend/tests/test_dashboard_boundaries.py` covers:

- Provider and Client root redirects;
- unauthenticated route redirects;
- Provider and Client page access;
- cross-dashboard page and API denial;
- ambiguous/invalid actor handling;
- cross-tenant learning resource denial;
- request-body `client_id` rejection;
- session-derived tenant use;
- registration workflow ownership and cross-tenant mutation denial;
- canonical route registration and legacy redirects.

The complete backend test suite and JavaScript syntax checks must remain green before removing a deprecated alias.
