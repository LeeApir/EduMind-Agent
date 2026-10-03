import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./ProductApp.vue";
import "./styles.css";

createApp(App).use(createPinia()).mount("#app");
