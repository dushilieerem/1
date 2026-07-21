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
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { CommunityFeedPage } from "./pages/CommunityFeedPage";
import { CommunityNewPage } from "./pages/CommunityNewPage";
import { CommunityPostPage } from "./pages/CommunityPostPage";
import { CommunityFavoritesPage } from "./pages/CommunityFavoritesPage";
import { CommunityMyPostsPage } from "./pages/CommunityMyPostsPage";

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

        <Route path="/community" element={<Authed><CommunityFeedPage /></Authed>} />
        <Route path="/community/new" element={<Authed><CommunityNewPage /></Authed>} />
        <Route path="/community/favorites" element={<Authed><CommunityFavoritesPage /></Authed>} />
        <Route path="/community/mine" element={<Authed><CommunityMyPostsPage /></Authed>} />
        <Route path="/community/post/:id" element={<Authed><CommunityPostPage /></Authed>} />

        <Route
          path="/data"
          element={
            <Authed>
              <PlaceholderPage
                title="数据"
                hint="行情由 YGQuant ResearchEngine 提供；本机薄 API 只托管 factor/ 文件。"
                cta={{ to: "/factor/library", label: "去因子库" }}
              />
            </Authed>
          }
        />

        <Route path="/strategy" element={<Authed><Navigate to="/strategy/research" replace /></Authed>} />
        <Route
          path="/strategy/research"
          element={
            <Authed>
              <PlaceholderPage
                title="策略研究"
                hint="策略研究模块建设中。"
                cta={{ to: "/factor/detect", label: "先做因子检测" }}
              />
            </Authed>
          }
        />
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
