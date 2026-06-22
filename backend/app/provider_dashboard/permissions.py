from enum import StrEnum


class ProviderPermission(StrEnum):
    DASHBOARD_ACCESS = "provider.dashboard.access"
    PLATFORM_READ = "provider.platform.read"
    PLATFORM_MANAGE = "provider.platform.manage"
    LEARNING_MANAGE = "provider.learning.manage"
    MESSAGE_DUMPS_MANAGE = "provider.message_dumps.manage"
    BILLING_MANAGE = "provider.billing.manage"
    SQLITE_MANAGE = "provider.sqlite.manage"


ALL_PROVIDER_PERMISSIONS = frozenset(permission.value for permission in ProviderPermission)
