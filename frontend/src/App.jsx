import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
// Register page removed — accounts are created during installation via install.py.
// To re-enable self-registration set REGISTRATION_ENABLED=true in the backend .env.
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Subscribers from "./pages/Subscribers";
import SubscriberListView from "./pages/SubscriberListView";
import Layout from "./components/Layout";
import Campaigns from "./pages/Campaigns";
import CreateCampaign from "./pages/CreateCampaign";
import EditCampaign from "./pages/EditCampaign";
import Analytics from "./pages/Analytics";
import CampaignAnalytics from "./pages/CampaignAnalytics";
import AuditTrail from "./components/AuditTrail";
import SettingsPage from "./pages/SettingsPage";
import EmailSettings from "./pages/EmailSettings";
import DomainSettings from "./pages/DomainSettings";
import UserSettings from "./pages/UserSettings";
import TemplatesPage from "./pages/TemplatesPage";
import SuppressionManagement from "./pages/SuppressionManagement";
import Segmentation from "./pages/Segmentation";
import ABTestingDashboard from "./pages/ABTestingDashboard";
import ABTestCreator from "./pages/ABTestCreator";
import ABTestResults from "./pages/ABTestResults";
import ABTestWinnerReport from "./pages/ABTestWinnerReport";
import AutomationDashboard from "./pages/AutomationDashboard";
import AutomationBuilder from "./pages/AutomationBuilder";
import AutomationAnalytics from "./pages/AutomationAnalytics";
import AutomationCampaignAnalytics from "./pages/AutomationCampaignAnalytics";
import OptInForm from "./pages/OptInForm";
import TrackingSettings from "./pages/TrackingSettings";
import LicenseSettings from "./pages/LicenseSettings";
import SnsWebhooksSettings from "./pages/SnsWebhooksSettings";
import DeliverabilityDashboard from "./pages/DeliverabilityDashboard";
import FeatureGate from "./components/FeatureGate";
import { isLoggedIn } from "./api";

// Wrapper: gives each edit session a unique key so React fully remounts the
// AutomationBuilder when navigating between different edit routes (or create → edit).
const AutomationEditRoute = () => {
  const { id } = useParams();
  return (
    <FeatureGate feature="automation">
      <AutomationBuilder key={id} />
    </FeatureGate>
  );
};

const App = () => {
  // Reads the non-httpOnly `logged_in` flag cookie set by the server on login.
  // The actual JWT lives in an httpOnly cookie — JS never touches it.

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/register" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/subscribe/:listId" element={<OptInForm />} />

        {/* Protected Routes */}
        {isLoggedIn() ? (
          <Route path="/" element={<Layout />}>
            {/* ── Always-available routes (all plans) ── */}
            <Route index element={<Dashboard />} />
            <Route path="subscribers" element={<Subscribers />} />
            <Route path="/subscribers/list/:listName" element={<SubscriberListView />} />
            <Route path="campaigns" element={<Campaigns />} />
            <Route path="campaigns/create" element={<CreateCampaign />} />
            <Route path="campaigns/:id/edit" element={<EditCampaign />} />
            <Route path="templates" element={<TemplatesPage />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="analytics/campaign/:campaignId" element={<CampaignAnalytics />} />
            <Route path="suppressions" element={<SuppressionManagement />} />
            <Route path="/segmentation" element={<FeatureGate feature="segmentation"><Segmentation /></FeatureGate>} />

            {/* ── A/B Testing (pro + enterprise) ── */}
            <Route
              path="ab-testing"
              element={<FeatureGate feature="ab_testing"><ABTestingDashboard /></FeatureGate>}
            />
            <Route
              path="ab-testing/create"
              element={<FeatureGate feature="ab_testing"><ABTestCreator /></FeatureGate>}
            />
            <Route
              path="ab-tests/:testId/results"
              element={<FeatureGate feature="ab_testing"><ABTestResults /></FeatureGate>}
            />
            <Route
              path="ab-tests/:testId/winner-report"
              element={<FeatureGate feature="ab_testing"><ABTestWinnerReport /></FeatureGate>}
            />
            <Route
              path="/ab-testing/edit/:testId"
              element={<FeatureGate feature="ab_testing"><ABTestCreator editMode /></FeatureGate>}
            />

            {/* ── Automation (enterprise only) ── */}
            <Route
              path="/automation"
              element={<FeatureGate feature="automation"><AutomationDashboard /></FeatureGate>}
            />
            <Route
              path="/automation/create"
              element={<FeatureGate feature="automation"><AutomationBuilder key="create" /></FeatureGate>}
            />
            <Route path="/automation/edit/:id" element={<AutomationEditRoute />} />
            <Route
              path="/automation/analytics/"
              element={<FeatureGate feature="automation"><AutomationAnalytics /></FeatureGate>}
            />
            <Route
              path="/automation/analytics/:id"
              element={<FeatureGate feature="automation"><AutomationCampaignAnalytics /></FeatureGate>}
            />

            {/* ── Deliverability dashboard (pro + enterprise) ── */}
            <Route
              path="deliverability"
              element={<FeatureGate feature="deliverability_dashboard"><DeliverabilityDashboard /></FeatureGate>}
            />

            {/* ── Audit trail (all plans — gated on license validity only) ── */}
            <Route
              path="audit"
              element={<FeatureGate feature="audit_trail"><AuditTrail /></FeatureGate>}
            />

            {/* ── Settings (always available) ── */}
            <Route path="settings" element={<SettingsPage />}>
              <Route path="user" element={<UserSettings />} />
              <Route path="email" element={<EmailSettings />} />
              <Route path="domain" element={<DomainSettings />} />
              <Route path="tracking" element={<TrackingSettings />} />
              <Route path="sns-webhooks" element={<SnsWebhooksSettings />} />
              <Route path="license" element={<LicenseSettings />} />
            </Route>
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" />} />
        )}
      </Routes>
    </BrowserRouter>
  );
};

export default App;
