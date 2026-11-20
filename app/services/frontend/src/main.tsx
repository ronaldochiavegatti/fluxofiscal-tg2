import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { FlagsProvider } from "./flags/FlagsProvider";
import { AparenciaProvider } from "./aparencia/AparenciaContext";
import { AvisosProvider } from "./components/Avisos";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <FlagsProvider>
      <AparenciaProvider>
        <AvisosProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AvisosProvider>
      </AparenciaProvider>
    </FlagsProvider>
  </React.StrictMode>
);
