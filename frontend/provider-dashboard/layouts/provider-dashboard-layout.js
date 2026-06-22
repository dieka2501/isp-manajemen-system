export class ProviderDashboardLayout {
  constructor({ navigation, permissions, routes }) {
    this.navigation = navigation;
    this.permissions = permissions;
    this.routes = routes;
  }

  mountNavigation(container) {
    if (!container) return;
    container.innerHTML = this.navigation
      .map((item, index) => `
        <button
          id="${item.id}"
          class="action-button ${index === 0 ? "action-primary is-active" : "action-secondary"} tab-button"
          type="button"
          role="tab"
          aria-selected="${index === 0 ? "true" : "false"}"
          data-view="${item.view}"
          data-route="${this.routes[item.view]}"
          data-permission="${item.permission}"
        >${item.label}</button>
      `)
      .join("");
  }
}
