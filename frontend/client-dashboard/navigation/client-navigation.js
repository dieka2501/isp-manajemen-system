import { clientPermissions } from "../permissions/client-permissions.js";

export const clientNavigation = Object.freeze([
  Object.freeze({ view: "overview", label: "Ringkasan", permission: clientPermissions.dashboardAccess }),
  Object.freeze({ view: "customers", label: "Customer", permission: clientPermissions.customersRead }),
  Object.freeze({ view: "packages", label: "Paket", permission: clientPermissions.packagesRead }),
  Object.freeze({ view: "billing", label: "Billing", permission: clientPermissions.billingRead }),
  Object.freeze({ view: "registrations", label: "Approval Registrasi", permission: clientPermissions.registrationsManage }),
  Object.freeze({ view: "learning", label: "Learn Process", permission: clientPermissions.learningManage }),
]);
