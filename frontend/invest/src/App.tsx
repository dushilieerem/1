import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./pages/Shell";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import Topic from "./pages/Topic";
import Stock from "./pages/Stock";
import Watch from "./pages/Watch";
import Portfolio from "./pages/Portfolio";
import Search from "./pages/Search";
import News from "./pages/News";
import Me from "./pages/Me";
import Community from "./pages/Community";
import PostDetail from "./pages/PostDetail";
import PostNew from "./pages/PostNew";
import { Privacy, Terms } from "./pages/Legal";

function Splash() {
  return (
    <div className="splash">
      <div className="brand-mark">SV</div>
      <p>加载 Invest…</p>
    </div>
  );
}

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Splash />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/terms" element={<Terms />} />
      <Route
        element={
          <Protected>
            <Shell />
          </Protected>
        }
      >
        <Route index element={<Home />} />
        <Route path="topic/:id" element={<Topic />} />
        <Route path="stock/:code" element={<Stock />} />
        <Route path="watch" element={<Watch />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="search" element={<Search />} />
        <Route path="news" element={<News />} />
        <Route path="community" element={<Community />} />
        <Route path="community/new" element={<PostNew />} />
        <Route path="community/:id" element={<PostDetail />} />
        <Route path="me" element={<Me />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
