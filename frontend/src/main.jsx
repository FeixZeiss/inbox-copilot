import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

// Entry point: mount the React app into the root DOM node.
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* StrictMode helps surface potential issues during development. */}
    <App />
  </React.StrictMode>
);
