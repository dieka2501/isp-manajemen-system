export const providerRoutes = Object.freeze({
  chatTestLab: "/sqlexplore/chat-test-lab",
  learning: "/sqlexplore/learning",
  dumps: "/sqlexplore/message-dumps",
  explorer: "/sqlexplore/sqlite",
});

export function providerViewFromPath(pathname) {
  const match = Object.entries(providerRoutes).find(([, path]) => path === pathname);
  return match?.[0] || "chatTestLab";
}
