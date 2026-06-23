import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { AppProviders } from "@/providers/app-providers"

import App from "./App.tsx"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>
)
