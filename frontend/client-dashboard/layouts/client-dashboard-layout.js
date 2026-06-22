export class ClientDashboardLayout {
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
          class="nav-item ${index === 0 ? "is-active" : ""}"
          type="button"
          data-view="${item.view}"
          data-route="${this.routes[item.view]}"
          data-permission="${item.permission}"
        >${item.label}</button>
      `)
      .join("");
  }
}
