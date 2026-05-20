// frontend/src/components/FeatureGate.jsx
//
// Wraps a route or section and shows an "upgrade required" screen when the
// current license plan does not include the requested feature.
//
// Usage in App.jsx:
//   <FeatureGate feature="ab_testing">
//     <ABTestingDashboard />
//   </FeatureGate>
//
// The gate is transparent while the license is still loading (brief window
// after login) so users don't see a flash of the locked screen.

import { useLicense, isFeatureEnabled } from "../contexts/LicenseContext";

const FEATURE_LABELS = {
  ab_testing:              "A/B Testing",
  automation:              "Automation",
  deliverability_dashboard:"Deliverability Dashboard",
  audit_trail:             "Audit Trail",
  api_access:              "API Access",
  multi_user:              "Multi-User / Team Roles",
};

const PLAN_NEXT = {
  starter:      "Pro",
  professional: "Enterprise / Agency",
  enterprise:   null,
};

function UpgradeRequired({ feature, plan }) {
  const label    = FEATURE_LABELS[feature] ?? feature;
  const nextPlan = PLAN_NEXT[plan] ?? "a higher";

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
      <div className="text-5xl mb-4">🔒</div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        {label} is not available on your plan
      </h2>
      <p className="text-gray-500 max-w-md mb-6">
        Your current plan is{" "}
        <span className="font-semibold capitalize">{plan}</span>. Upgrade to{" "}
        <span className="font-semibold">{nextPlan}</span> to unlock{" "}
        {label}.
      </p>
      <a
        href="https://zenipost.com/dashboard"
        target="_blank"
        rel="noopener noreferrer"
        className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 transition-colors"
      >
        Upgrade license →
      </a>
      <p className="text-xs text-gray-400 mt-4">
        After upgrading, reload the app or wait for the daily license sync.
      </p>
    </div>
  );
}

export default function FeatureGate({ feature, children }) {
  const { license } = useLicense();

  // While loading: render children optimistically (avoids flash for paying users)
  if (license.loading) return children;

  if (!isFeatureEnabled(feature, license)) {
    return <UpgradeRequired feature={feature} plan={license.plan} />;
  }

  return children;
}
