import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { HomePage } from "./pages/HomePage";
import { FactorLibraryPage } from "./pages/FactorLibraryPage";
import { FactorDetectPage } from "./pages/FactorDetectPage";
import { FactorDetectListPage } from "./pages/FactorDetectListPage";
import { FactorDetectHistoryPage } from "./pages/FactorDetectHistoryPage";
import { FactorDetectReportPage } from "./pages/FactorDetectReportPage";
import { FactorCustomPage } from "./pages/FactorCustomPage";
import { FactorDashboardPage } from "./pages/FactorDashboardPage";
import { StrategyResearchListPage } from "./pages/StrategyResearchListPage";
import { StrategyBacktestPage } from "./pages/StrategyBacktestPage";
import { StrategyReportPage } from "./pages/StrategyReportPage";
import { StrategyHistoryPage } from "./pages/StrategyHistoryPage";
import { DataKlinePanelPage } from "./pages/DataKlinePanelPage";
import { DataSearchResultsPage } from "./pages/DataSearchResultsPage";
import { DataSymbolOverviewPage } from "./pages/DataSymbolOverviewPage";
import { DataSymbolChartPage } from "./pages/DataSymbolChartPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { CommunityFeedPage } from "./pages/CommunityFeedPage";
import { CommunityNewPage } from "./pages/CommunityNewPage";
import { CommunityAiAssistPage } from "./pages/CommunityAiAssistPage";
import { CommunityPostPage } from "./pages/CommunityPostPage";
import { CommunityMePage } from "./pages/CommunityMePage";
import { CommunityProfilePage } from "./pages/CommunityProfilePage";
import { CommunityProfileEditPage } from "./pages/CommunityProfileEditPage";
import { CommunityProfileFollowsPage } from "./pages/CommunityProfileFollowsPage";

function Authed({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route path="/community" element={<CommunityFeedPage />} />
        <Route path="/community/new" element={<Authed><CommunityNewPage /></Authed>} />
        <Route path="/community/ai-assist" element={<Authed><CommunityAiAssistPage /></Authed>} />
        <Route path="/community/post/:id/edit" element={<Authed><CommunityNewPage /></Authed>} />
        <Route path="/community/favorites" element={<Navigate to="/community/me?tab=favorites" replace />} />
        <Route path="/community/mine" element={<Navigate to="/community/me?tab=mine" replace />} />
        <Route path="/community/drafts" element={<Navigate to="/community/me?tab=drafts" replace />} />
        <Route path="/community/messages" element={<Navigate to="/community/me?tab=messages" replace />} />
        <Route path="/community/mod" element={<Navigate to="/community/me?tab=mod" replace />} />
        <Route path="/community/me" element={<Authed><CommunityMePage /></Authed>} />
        <Route path="/community/post/:id" element={<CommunityPostPage />} />
        <Route path="/u/:username/edit" element={<Authed><CommunityProfileEditPage /></Authed>} />
        <Route
          path="/u/:username/following"
          element={<CommunityProfileFollowsPage kind="following" />}
        />
        <Route
          path="/u/:username/followers"
          element={<CommunityProfileFollowsPage kind="followers" />}
        />
        <Route path="/u/:username" element={<CommunityProfilePage />} />

        <Route path="/data" element={<Authed><Navigate to="/data/kline" replace /></Authed>} />
        <Route path="/data/kline" element={<Authed><DataKlinePanelPage /></Authed>} />
        <Route
          path="/data/kline/search"
          element={<Authed><DataSearchResultsPage /></Authed>}
        />
        <Route
          path="/data/watchlist"
          element={<Authed><PlaceholderPage title="自选股组合" hint="待开发。" /></Authed>}
        />
        <Route
          path="/data/symbol/:code/chart"
          element={<Authed><DataSymbolChartPage /></Authed>}
        />
        <Route
          path="/data/symbol/:code"
          element={<Authed><DataSymbolOverviewPage /></Authed>}
        />

        <Route path="/strategy" element={<Authed><Navigate to="/strategy/research" replace /></Authed>} />
        <Route path="/strategy/research" element={<Authed><StrategyResearchListPage /></Authed>} />
        <Route path="/strategy/research/report/:runId" element={<Authed><StrategyReportPage /></Authed>} />
        <Route path="/strategy/research/:projectId/history" element={<Authed><StrategyHistoryPage /></Authed>} />
        <Route path="/strategy/research/:projectId" element={<Authed><StrategyBacktestPage /></Authed>} />
        <Route
          path="/strategy/library"
          element={<Authed><PlaceholderPage title="策略库" hint="占位：策略库。" /></Authed>}
        />
        <Route
          path="/strategy/ai"
          element={<Authed><PlaceholderPage title="AI辅助策略设计" hint="占位入口。" /></Authed>}
        />

        <Route path="/factor" element={<Authed><Navigate to="/factor/library" replace /></Authed>} />
        <Route path="/factor/library" element={<Authed><FactorLibraryPage /></Authed>} />
        <Route path="/factor/library/custom/new" element={<Authed><FactorCustomPage /></Authed>} />
        <Route path="/factor/library/custom/:name" element={<Authed><FactorCustomPage /></Authed>} />
        <Route path="/factor/custom/new" element={<Navigate to="/factor/library/custom/new" replace />} />

        <Route path="/factor/detect" element={<Authed><FactorDetectListPage /></Authed>} />
        <Route path="/factor/detect/report/:runId" element={<Authed><FactorDetectReportPage /></Authed>} />
        <Route path="/factor/detect/:projectId/history" element={<Authed><FactorDetectHistoryPage /></Authed>} />
        <Route path="/factor/detect/:projectId" element={<Authed><FactorDetectPage /></Authed>} />

        <Route path="/factor/dashboard" element={<Authed><FactorDashboardPage /></Authed>} />
        <Route
          path="/factor/ai"
          element={<Authed><PlaceholderPage title="AI因子推荐" hint="占位入口。" /></Authed>}
        />
        <Route path="/factor/strategy" element={<Navigate to="/factor/dashboard" replace />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
