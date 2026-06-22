import { providerPermissions } from "../permissions/provider-permissions.js";

export const providerNavigation = Object.freeze([
  Object.freeze({ id: "learningTab", view: "learning", label: "Learning Queue", permission: providerPermissions.learningManage }),
  Object.freeze({ id: "dumpTab", view: "dumps", label: "Message Dumps", permission: providerPermissions.messageDumpsManage }),
  Object.freeze({ id: "explorerTab", view: "explorer", label: "SQLite Explorer", permission: providerPermissions.sqliteManage }),
]);
