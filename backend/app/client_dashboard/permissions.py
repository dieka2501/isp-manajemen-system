from enum import StrEnum


class ClientPermission(StrEnum):
    DASHBOARD_ACCESS = "client.dashboard.access"
    PROFILE_READ = "client.profile.read"
    CUSTOMERS_READ = "client.customers.read"
    PACKAGES_READ = "client.packages.read"
    BILLING_READ = "client.billing.read"
    REGISTRATIONS_MANAGE = "client.registrations.manage"
    LEARNING_MANAGE = "client.learning.manage"


ALL_CLIENT_PERMISSIONS = frozenset(permission.value for permission in ClientPermission)
