import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/access-keys": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/blobs": "http://localhost:8000",
      "/buckets": "http://localhost:8000",
      "/files": "http://localhost:8000",
      "/folders": "http://localhost:8000",
      "/users": "http://localhost:8000",
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
