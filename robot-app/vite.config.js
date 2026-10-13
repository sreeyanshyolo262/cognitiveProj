import { defineConfig } from "vite";

// Tauri expects a fixed dev port and must be able to reach the dev server from a phone.
export default defineConfig({
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: process.env.TAURI_DEV_HOST || false,
  },
});
