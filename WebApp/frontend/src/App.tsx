import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { HomePage } from "./pages/HomePage";
import { FactorLibraryPage } from "./pages/FactorLibraryPage";
import { FactorDetectPage } from "./pages/FactorDetectPage";
import { FactorDetectListPage } from "./pages/FactorDetectListPage";
import { FactorDetectHistoryPage } from "./pages/FactorDetectHistoryPage";
import { FactorDetectReportPage } from "./pages/FactorDetectReportPage";
import { FactorDashboardPage } from "./pages/FactorDashboardPage";
import { AiFactorGeneratePage } from "./pages/AiFactorGeneratePage";
import { AiStrategyGeneratePage } from "./pages/AiStrategyGeneratePage";
import { StrategyResearchListPage } from "./pages/StrategyResearchListPage";
import { StrategyBacktestPage } from "./pages/StrategyBacktestPage";
import { StrategyReportPage } from "./pages/StrategyReportPage";
import { StrategyHistoryPage } from "./pages/StrategyHistoryPage";
import { StrategyLibraryPage } from "./pages/StrategyLibraryPage";
import { DataKlinePanelPage } from "./pages/DataKlinePanelPage";
import { DataSearchResultsPage } from "./pages/DataSearchResultsPage";
import { DataSymbolOverviewPage } from "./pages/DataSymbolOverviewPage";
import { DataSymbolChartPage } from "./pages/DataSymbolChartPage";
import { WatchlistPage } from "./pages/WatchlistPage";
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
import { NewsPage } from "./pages/NewsPage";
import { NewsDetailPage } from "./pages/NewsDetailPage";
import { GlobalSearchPage } from "./pages/GlobalSearchPage";
import { HelpPage } from "./pages/ApiDocsPlaceholderPage";
import { AiChatPage } from "./pages/AiChatPage";
import { AgentGatherPage } from "./pages/AgentGatherPage";
import { AgentIdeaPage } from "./pages/AgentIdeaPage";
import { AgentFactorPage } from "./pages/AgentFactorPage";
import { AgentBacktestPage } from "./pages/AgentBacktestPage";
import { AgentEvalPage } from "./pages/AgentEvalPage";
import { AiHubPage } from "./pages/AiHubPage";

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

        <Route path="/search" element={<GlobalSearchPage />} />
        <Route path="/ai" element={<Authed><AiHubPage /></Authed>} />
        <Route path="/ai/chat" element={<Authed><AiChatPage /></Authed>} />
        <Route path="/ai/gather" element={<Authed><AgentGatherPage /></Authed>} />
        <Route path="/ai/idea" element={<Authed><AgentIdeaPage /></Authed>} />
        <Route path="/ai/factor" element={<Authed><AgentFactorPage /></Authed>} />
        <Route path="/ai/factor-backtest" element={<Authed><AgentBacktestPage /></Authed>} />
        <Route path="/ai/factor-eval" element={<Authed><AgentEvalPage /></Authed>} />
        <Route path="/community" element={<CommunityFeedPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/news/:id" element={<NewsDetailPage />} />
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
          element={<Authed><WatchlistPage /></Authed>}
        />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/help/:docId" element={<HelpPage />} />
        <Route path="/data/api-docs" element={<Navigate to="/help" replace />} />
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
          element={<Authed><StrategyLibraryPage /></Authed>}
        />
        <Route
          path="/strategy/library/archive/:archiveStrategyId"
          element={<Authed><StrategyReportPage /></Authed>}
        />
        <Route
          path="/strategy/ai"
          element={<Authed><AiStrategyGeneratePage /></Authed>}
        />

        <Route path="/factor" element={<Authed><Navigate to="/factor/library" replace /></Authed>} />
        <Route path="/factor/library" element={<Authed><FactorLibraryPage /></Authed>} />
        <Route path="/factor/library/custom/new" element={<Navigate to="/factor/library" replace />} />
        <Route path="/factor/library/custom/:name" element={<Navigate to="/factor/library" replace />} />
        <Route path="/factor/custom/new" element={<Navigate to="/factor/library" replace />} />

        <Route path="/factor/detect" element={<Authed><FactorDetectListPage /></Authed>} />
        <Route path="/factor/detect/report/:runId" element={<Authed><FactorDetectReportPage /></Authed>} />
        <Route path="/factor/detect/:projectId/history" element={<Authed><FactorDetectHistoryPage /></Authed>} />
        <Route path="/factor/detect/:projectId" element={<Authed><FactorDetectPage /></Authed>} />

        <Route path="/factor/dashboard" element={<Authed><FactorDashboardPage /></Authed>} />
        <Route
          path="/factor/ai"
          element={<Authed><AiFactorGeneratePage /></Authed>}
        />
        <Route path="/factor/strategy" element={<Navigate to="/factor/dashboard" replace />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
