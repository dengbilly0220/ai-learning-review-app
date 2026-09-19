import App from './App.vue';
import { createSSRApp } from 'vue';
import { applyStoredTheme } from './src/theme/ThemeManager';
export function createApp() {
    const app = createSSRApp(App);
    app.mixin({
        beforeMount() { applyStoredTheme(); },
        mounted() { applyStoredTheme(); },
        onShow() { applyStoredTheme(); }
    });
    return { app };
}
