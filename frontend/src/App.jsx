import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Register from './pages/Register';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Subscribers from './pages/Subscribers';
import SubscriberListView from './pages/SubscriberListView';
import Layout from './components/Layout';
import Campaigns from './pages/Campaigns';
import CreateCampaign from './pages/CreateCampaign';
import EditCampaign from './pages/EditCampaign';
import Analytics from './pages/Analytics';
import CampaignAnalytics from './pages/CampaignAnalytics';
import AuditTrail from './components/AuditTrail';
import SettingsPage from './pages/SettingsPage'; // ✅ Added import
import EmailSettings from './pages/EmailSettings';
import DomainSettings from './pages/DomainSettings';
import TemplatesPage from './pages/TemplatesPage';
import SuppressionManagement from './pages/SuppressionManagement';
import Segmentation from './pages/Segmentation';
import ABTestingDashboard from './pages/ABTestingDashboard';
import ABTestCreator from './pages/ABTestCreator';
import ABTestResults from './pages/ABTestResults';


// ✅ Default imports - NO curly braces
import AutomationDashboard from './pages/AutomationDashboard';
import AutomationBuilder from './pages/AutomationBuilder';
import AutomationAnalytics from './pages/AutomationAnalytics';
import AutomationCampaignAnalytics from './pages/AutomationCampaignAnalytics';
import LandingPage from './pages/LandingPage';


const App = () => {
  const isLoggedIn = !!localStorage.getItem('token');

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/landing" element={<LandingPage />} />
        <Route path="/register" element={<Register />} />
        <Route path="/login" element={<Login />} />

        {/* Protected Routes */}
        {isLoggedIn ? (
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="subscribers" element={<Subscribers />} />
            <Route path="/subscribers/list/:listName" element={<SubscriberListView />} />
            <Route path="campaigns" element={<Campaigns />} />
            <Route path="campaigns/create" element={<CreateCampaign />} />
            <Route path="campaigns/:id/edit" element={<EditCampaign />} />
            <Route path="templates" element={<TemplatesPage />}      />         
            <Route path="analytics" element={<Analytics />} />
            <Route path="analytics/campaign/:campaignId" element={<CampaignAnalytics />} />
            <Route path="audit" element={<AuditTrail />} />
            <Route path="suppressions" element={<SuppressionManagement />} />
            <Route path="/segmentation" element={<Segmentation />} />
            <Route path="ab-testing" element={<ABTestingDashboard />} />
            <Route path="ab-testing/create" element={<ABTestCreator />} />
            <Route path="ab-tests/:testId/results" element={<ABTestResults />} />
                

            {/* New Automation Routes */}
            <Route path="/automation" element={<AutomationDashboard />} />
            <Route path="/automation/create" element={<AutomationBuilder />} />
            <Route path="/automation/edit/:id" element={<AutomationBuilder />} />
                  <Route path="/automation/analytics/" element={<AutomationAnalytics />} />
            <Route path="/automation/analytics/:id" element={<AutomationCampaignAnalytics />} />
                  
            {/* Settings with nested tabs */}
            <Route path="settings" element={<SettingsPage />}>
              <Route path="email" element={<EmailSettings />} />
              <Route path="domain" element={<DomainSettings />} />
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


