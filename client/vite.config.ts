import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // Recharts alone is ~500 kB; one chunk is fine for a dashboard this size.
  build: { chunkSizeWarningLimit: 900 },
});
