import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Serve assets from /static so the backend can mount the built files there.
  base: "/static/",
  server: {
    port: 5173,
    proxy: {
      // Dev-only proxy so /api calls hit the FastAPI server.
      "/api": "http://localhost:8000",
    },
  },
});
