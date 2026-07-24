import { Outlet } from "react-router-dom";
import { ConfirmProvider } from "./ConfirmDialog";
import { Navbar } from "./Navbar";

export function Layout() {
  return (
    <ConfirmProvider>
      <div className="min-h-screen bg-slate-50">
        <Navbar />
        <main>
          <Outlet />
        </main>
      </div>
    </ConfirmProvider>
  );
}
