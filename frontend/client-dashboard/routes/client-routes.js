export const clientRoutes = Object.freeze({
  overview: "/client-dashboard/overview",
  customers: "/client-dashboard/customers",
  packages: "/client-dashboard/packages",
  billing: "/client-dashboard/billing",
  registrations: "/client-dashboard/registrations",
  learning: "/client-dashboard/learning",
});

export function clientViewFromPath(pathname) {
  const match = Object.entries(clientRoutes).find(([, path]) => path === pathname);
  return match?.[0] || "overview";
}
