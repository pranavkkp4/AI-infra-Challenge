import { Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "./components/Shell";
import { AssetsPage } from "./pages/AssetsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { InvestigationPage } from "./pages/InvestigationPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ReviewPage } from "./pages/ReviewPage";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<DashboardPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="investigations/:incidentId?" element={<InvestigationPage />} />
        <Route path="reviews" element={<ReviewPage />} />
        <Route path="reports" element={<ReportsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
