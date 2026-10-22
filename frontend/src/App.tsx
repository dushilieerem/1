import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";

/** 路由懒加载：新标签不必一次解析全站页面，减轻内存与首屏白屏 */
const HomePage = lazy(() => import("./pages/HomePage").then((m) => ({ default: m.HomePage })));
const FactorLibraryPage = lazy(() =>
  import("./pages/FactorLibraryPage").then((m) => ({ default: m.FactorLibraryPage })),
);
const FactorDetectPage = lazy(() =>
  import("./pages/FactorDetectPage").then((m) => ({ default: m.FactorDetectPage })),
);
const FactorDetectListPage = lazy(() =>
  import("./pages/FactorDetectListPage").then((m) => ({ default: m.FactorDetectListPage })),
);
const FactorDetectHistoryPage = lazy(() =>
  import("./pages/FactorDetectHistoryPage").then((m) => ({ default: m.FactorDetectHistoryPage })),
);
const FactorDetectReportPage = lazy(() =>
  import("./pages/FactorDetectReportPage").then((m) => ({ default: m.FactorDetectReportPage })),
);
const FactorDashboardPage = lazy(() =>
  import("./pages/FactorDashboardPage").then((m) => ({ default: m.FactorDashboardPage })),
);
const AiFactorGeneratePage = lazy(() =>
  import("./pages/AiFactorGeneratePage").then((m) => ({ default: m.AiFactorGeneratePage })),
);
const AiStrategyGeneratePage = lazy(() =>
  import("./pages/AiStrategyGeneratePage").then((m) => ({ default: m.AiStrategyGeneratePage })),
);
const StrategyResearchListPage = lazy(() =>
  import("./pages/StrategyResearchListPage").then((m) => ({
    default: m.StrategyResearchListPage,
  })),
);
const StrategyBacktestPage = lazy(() =>
  import("./pages/StrategyBacktestPage").then((m) => ({ default: m.StrategyBacktestPage })),
);
const StrategyReportPage = lazy(() =>
  import("./pages/StrategyReportPage").then((m) => ({ default: m.StrategyReportPage })),
);
const StrategyHistoryPage = lazy(() =>
  import("./pages/StrategyHistoryPage").then((m) => ({ default: m.StrategyHistoryPage })),
);
const StrategyLibraryPage = lazy(() =>
  import("./pages/StrategyLibraryPage").then((m) => ({ default: m.StrategyLibraryPage })),
);
const StrategyPlazaPage = lazy(() =>
  import("./pages/StrategyPlazaPage").then((m) => ({ default: m.StrategyPlazaPage })),
);
const StrategyPlazaDetailPage = lazy(() =>
  import("./pages/StrategyPlazaDetailPage").then((m) => ({
    default: m.StrategyPlazaDetailPage,
  })),
);
const PaperTradingListPage = lazy(() =>
  import("./pages/PaperTradingListPage").then((m) => ({
    default: m.PaperTradingListPage,
  })),
);
const PaperAccountPage = lazy(() =>
  import("./pages/PaperAccountPage").then((m) => ({
    default: m.PaperAccountPage,
  })),
);
const DataKlinePanelPage = lazy(() =>
  import("./pages/DataKlinePanelPage").then((m) => ({ default: m.DataKlinePanelPage })),
);
const DataFieldsPage = lazy(() =>
  import("./pages/DataFieldsPage").then((m) => ({ default: m.DataFieldsPage })),
);
const DataSearchResultsPage = lazy(() =>
  import("./pages/DataSearchResultsPage").then((m) => ({ default: m.DataSearchResultsPage })),
);
const DataSymbolOverviewPage = lazy(() =>
  import("./pages/DataSymbolOverviewPage").then((m) => ({ default: m.DataSymbolOverviewPage })),
);
const DataSymbolChartPage = lazy(() =>
  import("./pages/DataSymbolChartPage").then((m) => ({ default: m.DataSymbolChartPage })),
);
const WatchlistPage = lazy(() =>
  import("./pages/WatchlistPage").then((m) => ({ default: m.WatchlistPage })),
);
const LoginPage = lazy(() => import("./pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() =>
  import("./pages/RegisterPage").then((m) => ({ default: m.RegisterPage })),
);
const CommunityFeedPage = lazy(() =>
  import("./pages/CommunityFeedPage").then((m) => ({ default: m.CommunityFeedPage })),
);
const CommunityNewPage = lazy(() =>
  import("./pages/CommunityNewPage").then((m) => ({ default: m.CommunityNewPage })),
);
const CommunityAiAssistPage = lazy(() =>
  import("./pages/CommunityAiAssistPage").then((m) => ({ default: m.CommunityAiAssistPage })),
);
const CommunityPostPage = lazy(() =>
  import("./pages/CommunityPostPage").then((m) => ({ default: m.CommunityPostPage })),
);
const CommunityMePage = lazy(() =>
  import("./pages/CommunityMePage").then((m) => ({ default: m.CommunityMePage })),
);
const CommunityProfilePage = lazy(() =>
  import("./pages/CommunityProfilePage").then((m) => ({ default: m.CommunityProfilePage })),
);
const CommunityProfileEditPage = lazy(() =>
  import("./pages/CommunityProfileEditPage").then((m) => ({
    default: m.CommunityProfileEditPage,
  })),
);
const CommunityProfileFollowsPage = lazy(() =>
  import("./pages/CommunityProfileFollowsPage").then((m) => ({
    default: m.CommunityProfileFollowsPage,
  })),
);
const NewsPage = lazy(() => import("./pages/NewsPage").then((m) => ({ default: m.NewsPage })));
const NewsDetailPage = lazy(() =>
  import("./pages/NewsDetailPage").then((m) => ({ default: m.NewsDetailPage })),
);
const GlobalSearchPage = lazy(() =>
  import("./pages/GlobalSearchPage").then((m) => ({ default: m.GlobalSearchPage })),
);
const HelpPage = lazy(() =>
  import("./pages/ApiDocsPlaceholderPage").then((m) => ({ default: m.HelpPage })),
);
const AiChatPage = lazy(() =>
  import("./pages/AiChatPage").then((m) => ({ default: m.AiChatPage })),
);
const AgentGatherPage = lazy(() =>
  import("./pages/AgentGatherPage").then((m) => ({ default: m.AgentGatherPage })),
);
const AgentIdeaPage = lazy(() =>
  import("./pages/AgentIdeaPage").then((m) => ({ default: m.AgentIdeaPage })),
);
const AgentFactorPage = lazy(() =>
  import("./pages/AgentFactorPage").then((m) => ({ default: m.AgentFactorPage })),
);
const AgentBacktestPage = lazy(() =>
  import("./pages/AgentBacktestPage").then((m) => ({ default: m.AgentBacktestPage })),
);
const AgentEvalPage = lazy(() =>
  import("./pages/AgentEvalPage").then((m) => ({ default: m.AgentEvalPage })),
);
const AiHubPage = lazy(() => import("./pages/AiHubPage").then((m) => ({ default: m.AiHubPage })));

function Authed({ children }: { children: ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}

function RouteFallback() {
  const { pathname } = useLocation();
  const detectFlow =
    pathname.startsWith("/factor/detect/") &&
    !pathname.endsWith("/history") &&
    !pathname.includes("/report/");
  if (detectFlow) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center bg-[#f0f2f5] text-slate-600">
        <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-slate-200 border-t-red-600" />
        <p className="mt-3 text-sm">正在加载检测项目…</p>
      </div>
    );
  }
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
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
          <Route
            path="/data/fields"
            element={<Authed><DataFieldsPage /></Authed>}
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

          <Route path="/paper" element={<Authed><PaperTradingListPage /></Authed>} />
          <Route path="/paper/:accountId" element={<Authed><PaperAccountPage /></Authed>} />

          <Route path="/strategy" element={<Navigate to="/strategy/plaza" replace />} />
          <Route path="/strategy/plaza" element={<StrategyPlazaPage />} />
          <Route path="/strategy/plaza/:id" element={<StrategyPlazaDetailPage />} />
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
    </Suspense>
  );
}
