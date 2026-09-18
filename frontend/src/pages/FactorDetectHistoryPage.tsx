import { Navigate, useParams } from "react-router-dom";

/** 旧「检测列表」按项目维度 → 收敛到全局检测报告 */
export function FactorDetectHistoryPage() {
  const { projectId = "" } = useParams();
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return <Navigate to={`/factor/detect${q}`} replace />;
}
