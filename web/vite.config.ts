import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api -> FastAPI backend during dev so there are no CORS surprises.
// NOTE: the backend routes are literally prefixed with /api (e.g. /api/channels),
// so we must NOT strip /api here.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
