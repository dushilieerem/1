import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import ErrorBoundary from "./ErrorBoundary";
import { AuthProvider } from "./auth";
import { LocaleProvider } from "./i18n";
import { ToastProvider } from "./toast";
import "./styles.css";

const basename = window.location.pathname.startsWith("/mobile") ? "/mobile" : "/";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter basename={basename}>
        <AuthProvider>
          <LocaleProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </LocaleProvider>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>,
);
