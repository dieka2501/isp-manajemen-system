# Dashboard Separation Inventory

Inventory date: 2026-06-22

## Pre-change implementation summary

```text
Target actor: Provider User and Client User (Subscriber remains public/non-dashboard)
Target dashboard: Provider `/sqlexplore/*`; Client `/client-dashboard/*`
Existing route: `/`, `/dashboard`, `/client-dashboard`, `/sqlexplorer`, public registration/payment routes
Target route: auth-aware `/`; Provider `/sqlexplore/*`; Client `/client-dashboard/*`; explicit `/login/*` and `/unauthorized`
Required permission: provider permission per operation; client dashboard access bound to the authenticated client session
Tenant scope: Provider may operate cross-tenant per permission; Client is always scoped by `session.client_id`
Affected frontend modules: `frontend/index.html`, `frontend/app.js`, `frontend/sqlexplorer.html`, `frontend/sqlexplorer.js`, dashboard-specific route/navigation/layout modules
Affected backend modules: `app.main`, API router/modules, dashboard auth services, new auth/provider/client route and permission modules
Migration risk: High — canonical provider path changes, API namespaces change, and client auth moves from browser-only Bearer state to a server-visible session cookie
```

## Existing page routes and ownership

| Existing Route | Current Component | Current User | Intended Dashboard | Category | Action |
| --- | --- | --- | --- | --- | --- |
| `/` | `frontend/index.html` | Client User | Authentication router | Deprecated route | Replace page implementation with actor-aware redirect |
| `/dashboard` | `frontend/index.html` | Client User | Client | Deprecated route | Redirect to `/client-dashboard` |
| `/dashboard/` | `frontend/index.html` | Client User | Client | Deprecated route | Redirect to `/client-dashboard` |
| `/client-dashboard` | `frontend/index.html` | Client User | Client | Client | Keep as canonical protected route |
| `/client-dashboard/` | `frontend/index.html` | Client User | Client | Client | Canonicalize to `/client-dashboard` |
| `/client-dashboard/registrations` | Client approval view | Client User | Client | Client | Canonical tenant-scoped registration workflow |
| `/sqlexplore/registrations` | Provider registration view | Provider User | Client | Deprecated route | Remove feature implementation; Client owns `/client-dashboard/registrations` |
| `/sqlexplorer` | `frontend/sqlexplorer.html` | Provider User | Provider | Deprecated route | Redirect to canonical `/sqlexplore` |
| `/sqlexplorer/` | `frontend/sqlexplorer.html` | Provider User | Provider | Deprecated route | Redirect to canonical `/sqlexplore` |
| `/register/{token}` | `frontend/registration.html` | Subscriber | Public | Shared public route | Keep |
| `/payment/{token}` | `frontend/payment.html` | Subscriber | Public | Shared public route | Keep |
| `/health` | `health_check` | Monitoring/public | Public | Shared public route | Keep |

No page route remains `Unknown`: usage, data source, API calls, and menu entry were traceable from the current frontend and backend.

## Existing navigation ownership

| Navigation item | Current page | APIs/data | Intended dashboard | Action |
| --- | --- | --- | --- | --- |
| Ringkasan | Client dashboard | Client summary and recent billing | Client | Keep in `clientNavigation` |
| Customer | Client dashboard | Tenant customers | Client | Keep in `clientNavigation` |
| Paket | Client dashboard | Tenant packages | Client | Keep in `clientNavigation` |
| Billing | Client dashboard | Tenant billing | Client | Keep in `clientNavigation` |
| Approval Registrasi | Operations dashboard | Registration approval/payment/activation | Client | Move to `clientNavigation`; scope with authenticated Client session |
| Learn Process | Client dashboard | Tenant learning queue and preview | Client | Keep in `clientNavigation` |
| Learning Queue | Operations dashboard | Cross-tenant learning queue | Provider | Keep in `providerNavigation` |
| Message Dumps | Operations dashboard | Cross-tenant message review | Provider | Keep in `providerNavigation` |
| SQLite Explorer | Operations dashboard | Configured database sources and raw SQL | Provider | Keep in `providerNavigation` |

The two menus are separate in the existing HTML but hard-coded. They will become separate configuration modules; there will be no combined browser-filtered menu.

## Existing API ownership and migration map

| Existing API | Current authorization | Data scope | Category | Target/action |
| --- | --- | --- | --- | --- |
| `/api/v1` | None | System | Shared public API | Keep |
| `/api/v1/webhooks/fonnte` GET/POST | Optional webhook secret | Device/client resolved from payload | Shared integration API | Keep; not a dashboard API |
| `/api/v1/sqlite/auth/*` | Provider password/cookie | Provider session | Authentication API | Move to `/api/v1/provider/auth/*` |
| `/api/v1/sqlite/sources` | Provider cookie | Cross-source | Provider API | Move to `/api/v1/provider/sqlite/sources` |
| `/api/v1/sqlite/tables*` | Provider cookie | Cross-source | Provider API | Move to `/api/v1/provider/sqlite/tables*` |
| `/api/v1/sqlite/query` | Provider cookie | Cross-source | Provider API | Move to `/api/v1/provider/sqlite/query` |
| `/api/v1/sqlite/billing-import*` | Provider cookie | Arbitrary selected client/device | Provider API | Move to `/api/v1/provider/sqlite/billing-import*` |
| `/api/v1/chat/accounts` GET/POST | None | Cross-tenant | Provider API | Move under `/api/v1/provider/chat`; require platform-manage permission |
| `/api/v1/chat/clients` GET/POST | None | Cross-tenant | Provider API | Move under `/api/v1/provider/chat`; require platform-manage permission |
| `/api/v1/chat/devices` POST | None | Selected client | Provider API | Move under `/api/v1/provider/chat`; require platform-manage permission |
| `/api/v1/chat/stock-products` GET/POST | None | Caller-selected client/device | Provider API | Move under `/api/v1/provider/chat`; require platform-manage permission |
| `/api/v1/chat/internet-packages` GET | None | Caller-selected client/device | Provider API | Move under `/api/v1/provider/chat`; require platform-read permission |
| `/api/v1/chat/agent/preview` POST | None | Cross-tenant catalog | Provider API | Move under `/api/v1/provider/chat`; require learning-manage permission |
| `/api/v1/chat/learning/*` | Provider cookie | Cross-tenant | Provider API | Move under `/api/v1/provider/chat`; require learning-manage permission |
| `/api/v1/chat/conversations*` | None | Caller-selected client/device | Provider API | Move under `/api/v1/provider/chat`; require platform-read permission |
| `/api/v1/client-dashboard/auth/login` | Client credentials | Authenticated client | Authentication API | Canonicalize to `/api/v1/client/auth/login`; retain temporary API alias |
| `/api/v1/client-dashboard/auth/me` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/auth/me`; retain temporary API alias |
| `/api/v1/client-dashboard/profile` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/profile`; retain temporary API alias |
| `/api/v1/client-dashboard/summary` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/summary`; retain temporary API alias |
| `/api/v1/client-dashboard/devices` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/devices`; retain temporary API alias |
| `/api/v1/client-dashboard/customers` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/customers`; retain temporary API alias |
| `/api/v1/client-dashboard/packages` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/packages`; retain temporary API alias |
| `/api/v1/client-dashboard/billing` | Bearer token | Session client | Client API | Canonicalize to `/api/v1/client/billing`; retain temporary API alias |
| `/api/v1/registrations/admin/items` | Provider cookie | Cross-tenant registrations | Client API | Replace with `/api/v1/client/registrations/items`; derive tenant from session |
| `/api/v1/registrations/admin/{id}/approve` | Provider cookie | Cross-tenant mutation | Client API | Replace with `/api/v1/client/registrations/{id}/approve`; verify resource ownership |
| `/api/v1/registrations/admin/{id}/payment` | Provider cookie | Cross-tenant mutation | Client API | Replace with `/api/v1/client/registrations/{id}/payment`; verify resource ownership |
| `/api/v1/registrations/admin/{id}/activate` | Provider cookie | Cross-tenant mutation | Client API | Replace with `/api/v1/client/registrations/{id}/activate`; verify resource ownership |
| `/api/v1/client-dashboard/learning/*` | Bearer token | Session client plus resource ownership check | Client API | Canonicalize to `/api/v1/client/learning/*`; retain temporary API alias |
| `/api/v1/client-dashboard/agent/preview` | Bearer token | Session client/device | Client API | Canonicalize to `/api/v1/client/agent/preview`; retain temporary API alias |
| `/api/v1/registrations/public/{token}*` | Public token | Token-owned registration | Shared public API | Keep |
| `/api/v1/registrations/virtual-account/callback` | Payment webhook secret when configured | Target registration | Shared integration API | Keep |
| `/api/v1/registrations/admin/message-dumps*` | Provider cookie | Cross-tenant internal review | Provider API | Move to `/api/v1/provider/message-dumps*`; require `provider.message_dumps.manage` |

## Existing roles and permissions

| Actor | Existing proof | Existing permissions | Gap to close |
| --- | --- | --- | --- |
| Provider User | Signed cookie created from one shared dashboard password | Boolean authenticated/not-authenticated only | Add explicit provider actor claim and named backend permissions |
| Client User | Signed Bearer token whose `sub` is a client ID | Boolean valid token plus active-client lookup | Add explicit client actor claim, server-visible HttpOnly session cookie, and named client permissions |
| Subscriber | Public registration token | Registration/payment flow only | Remains outside dashboard authorization |

## Tenant-isolation findings

- Canonical client endpoints already derive `client_id` from the signed token subject and pass it to tenant-scoped store methods.
- Client device selection is checked against devices returned for the authenticated client.
- Learning-item mutation checks `item.client_id` against the authenticated client before mapping.
- Registration list and every approval/payment/activation mutation filter the resource with `session.client_id`; foreign registrations resolve as not found.
- The current client token only lives in `localStorage`, so the server cannot make an authentication-aware decision at `/`; this will be migrated to an HttpOnly cookie while retaining Bearer compatibility for the API migration window.
- Several current `/api/v1/chat/*` endpoints accept arbitrary `client_id` and are unauthenticated. They are cross-tenant Provider operations, not Client APIs, and must move behind Provider permission checks.
- Client request bodies will reject unknown fields so injected `client_id` values cannot silently influence a Client operation.
