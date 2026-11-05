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
import Agents from "./pages/Agents";
import Community from "./pages/Community";
import PostDetail from "./pages/PostDetail";
import PostNew from "./pages/PostNew";
import Notifications from "./pages/Notifications";
import QuantHome from "./pages/QuantHome";
import FactorLibrary from "./pages/FactorLibrary";
import StrategyLibrary from "./pages/StrategyLibrary";
import EtfDetail from "./pages/EtfDetail";
import Learn from "./pages/Learn";
import AiChat from "./pages/AiChat";
import Compare from "./pages/Compare";
import Paper from "./pages/Paper";
import QuantDashboard from "./pages/QuantDashboard";
import QuantSelect from "./pages/QuantSelect";
import QuantSignals from "./pages/QuantSignals";
import StrategyPlaza from "./pages/StrategyPlaza";
import QuantFactors from "./pages/QuantFactors";
import QuantStrategies from "./pages/QuantStrategies";
import QuantStrategyDetail from "./pages/QuantStrategyDetail";
import QuantBacktestList from "./pages/QuantBacktestList";
import QuantBacktestReport from "./pages/QuantBacktestReport";
import QuantPaperList from "./pages/QuantPaperList";
import QuantPaperNew from "./pages/QuantPaperNew";
import QuantPaperDetail from "./pages/QuantPaperDetail";
import { Privacy, Terms } from "./pages/Legal";
import { useLocale } from "./i18n";

function Splash() {
  const { t } = useLocale();
  return (
    <div className="splash">
      <div className="brand-mark">SV</div>
      <p>{t("加载 Invest…", "Loading Invest…")}</p>
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
        <Route path="notifications" element={<Notifications />} />
        <Route path="quant" element={<QuantHome />} />
        <Route path="quant/factors" element={<QuantFactors />} />
        <Route path="quant/strategies" element={<QuantStrategies />} />
        <Route path="quant/strategies/:id" element={<QuantStrategyDetail />} />
        <Route path="quant/backtests" element={<QuantBacktestList />} />
        <Route path="quant/backtests/:id" element={<QuantBacktestReport />} />
        <Route path="quant/papers" element={<QuantPaperList />} />
        <Route path="quant/papers/new" element={<QuantPaperNew />} />
        <Route path="quant/papers/:id" element={<QuantPaperDetail />} />
        <Route path="quant/factor" element={<FactorLibrary />} />
        <Route path="quant/strategy" element={<StrategyLibrary />} />
        <Route path="quant/dashboard" element={<QuantDashboard />} />
        <Route path="quant/select" element={<QuantSelect />} />
        <Route path="quant/signals" element={<QuantSignals />} />
        <Route path="quant/plaza" element={<StrategyPlaza />} />
        <Route path="ai" element={<AiChat />} />
        <Route path="compare/:a" element={<Compare />} />
        <Route path="compare/:a/:b" element={<Compare />} />
        <Route path="paper" element={<Paper />} />
        <Route path="etf/:code" element={<EtfDetail />} />
        <Route path="learn" element={<Learn />} />
        <Route path="me" element={<Me />} />
        <Route path="agents" element={<Agents />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
