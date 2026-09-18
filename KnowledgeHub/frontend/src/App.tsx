import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RequireAdmin } from "./components/RequireAdmin";
import { HomePage } from "./pages/HomePage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { RetrievalTestPage } from "./pages/RetrievalTestPage";
import { ChatsPage } from "./pages/ChatsPage";
import { ChatDetailPage } from "./pages/ChatDetailPage";
import { FilesPage } from "./pages/FilesPage";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { ModelProvidersPage } from "./pages/settings/ModelProvidersPage";
import { ModelTestPage } from "./pages/settings/ModelTestPage";
import { ApiDocsPage } from "./pages/settings/ApiDocsPage";
import { GuidePage } from "./pages/settings/GuidePage";
import { AccountPage } from "./pages/settings/AccountPage";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAdmin>
            <AppShell />
          </RequireAdmin>
        }
      >
        <Route path="/" element={<HomePage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/datasets/:id" element={<DatasetDetailPage />} />
        <Route path="/datasets/:id/documents/:docId" element={<DocumentDetailPage />} />
        <Route path="/datasets/:id/search" element={<RetrievalTestPage />} />
        <Route path="/chats" element={<ChatsPage />} />
        <Route path="/chats/:id" element={<ChatDetailPage />} />
        <Route path="/files" element={<FilesPage />} />
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="guide" replace />} />
          <Route path="guide" element={<GuidePage />} />
          <Route path="models" element={<ModelProvidersPage />} />
          <Route path="models/test" element={<ModelTestPage />} />
          <Route path="api" element={<ApiDocsPage />} />
          <Route path="account" element={<AccountPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
