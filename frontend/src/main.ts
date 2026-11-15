import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./assets/theme.css";
import { configureApi } from "@/composables/useApi";

configureApi({
  baseUrl: "/api/v1",
  onUnauthorized: () => router.push({ name: "login" }),
});

// Prime the CSRF cookie before any POST. Prod: shell template sets it
// via {{ csrf_token }}. Dev: Vite serves the page so no Django render
// has happened — hit the dedicated endpoint to seed it.
void (async () => {
  const has = document.cookie.split(";").some((c) => c.trim().startsWith("csrftoken="));
  if (has) return;
  try {
    await fetch("/api/v1/csrf/", { credentials: "include" });
  } catch {
    /* login POST will 403 if this fails; nothing else to do */
  }
})();

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
