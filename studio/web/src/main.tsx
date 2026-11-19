import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { captureUrlParams } from "./api/token";
import "./index.css";

captureUrlParams();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
