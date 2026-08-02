import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend so the frontend can use
// relative URLs. Override the target if your backend runs elsewhere.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/agent": "http://localhost:8000",
      "/regions": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
