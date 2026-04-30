// frontend/src/components/Sidebar.jsx
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useUser } from "../contexts/UserContext";
import { useSettings } from "../contexts/SettingsContext";
import ZeniPostLogo from "./ZeniPostLogo";

function getAvatarColor(name) {
  if (!name) return "bg-gray-400";
  const colors = [
    "bg-blue-500", "bg-violet-500", "bg-emerald-500", "bg-amber-500",
    "bg-rose-500",  "bg-cyan-500",   "bg-indigo-500",  "bg-teal-500",
  ];
  return colors[name.charCodeAt(0) % colors.length];
}

export default function Sidebar() {
  const { pathname } = useLocation();
  const navigate    = useNavigate();
  const { user }    = useUser();
  const { t }       = useSettings();   // ← must be inside the component

  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed,  setCollapsed]  = useState(false);

  // Built inside the component so t() is available
  const NAV_GROUPS = [
    {
      label: t("nav.group.overview"),
      items: [
        { to: "/",         label: t("nav.dashboard"),  icon: "🏠", description: t("nav.dashboard.sub") },
        { to: "/analytics",label: t("nav.analytics"),  icon: "📊", description: t("nav.analytics.sub") },
      ],
    },
    {
      label: t("nav.group.audience"),
      items: [
        { to: "/subscribers",  label: t("nav.subscribers"),  icon: "👥", description: t("nav.subscribers.sub") },
        { to: "/segmentation", label: t("nav.segments"),     icon: "🎯", description: t("nav.segments.sub") },
        { to: "/suppressions", label: t("nav.suppressions"), icon: "🛡️", description: t("nav.suppressions.sub") },
      ],
    },
    {
      label: t("nav.group.sending"),
      items: [
        { to: "/campaigns",  label: t("nav.campaigns"),  icon: "📢", description: t("nav.campaigns.sub") },
        { to: "/templates",  label: t("nav.templates"),  icon: "📄", description: t("nav.templates.sub") },
        { to: "/ab-testing", label: t("nav.abTesting"),  icon: "⚖️ ", description: t("nav.abTesting.sub") },
        { to: "/automation", label: t("nav.automation"), icon: "🤖", description: t("nav.automation.sub") },
      ],
    },
    {
      label: t("nav.group.system"),
      items: [
        { to: "/audit",          label: t("nav.audit"),    icon: "📋", description: t("nav.audit.sub") },
        { to: "/settings/email", label: t("nav.settings"), icon: "⚙️", description: t("nav.settings.sub") },
      ],
    },
  ];

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  const avatarLetter = user?.name ? user.name.charAt(0).toUpperCase() : "?";
  const displayName  = user?.name
    ? user.name.charAt(0).toUpperCase() + user.name.slice(1)
    : "Unknown";

  // ── Single nav item ───────────────────────────────────────
  const NavItem = ({ item }) => {
    const isActive =
      pathname === item.to || (item.to !== "/" && pathname.startsWith(item.to));

    return (
      <NavLink
        to={item.to}
        title={collapsed ? item.label : undefined}
        aria-label={item.label}
        onClick={() => setMobileOpen(false)}
        className={({ isActive: navActive }) =>
          [
            "flex items-center rounded-lg transition-all duration-150 group relative",
            collapsed ? "justify-center px-2 py-2.5" : "px-3 py-2.5",
            navActive || isActive
              ? "bg-blue-50 text-blue-700"
              : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
          ].join(" ")
        }
      >
        {({ isActive: navActive }) => {
          const active = navActive || isActive;
          return (
            <>
              <span
                className={[
                  "absolute left-0 w-0.5 h-5 rounded-r-full transition-all",
                  active ? "bg-blue-400" : "bg-transparent",
                ].join(" ")}
              />
              <span className={`text-base flex-shrink-0 ${collapsed ? "" : "mr-3"}`}>
                {item.icon}
              </span>
              {!collapsed && (
                <div className="flex-1 min-w-0 overflow-hidden">
                  <p className={`text-sm font-medium leading-none truncate ${active ? "text-blue-700" : ""}`}>
                    {item.label}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5 truncate">
                    {item.description}
                  </p>
                </div>
              )}
            </>
          );
        }}
      </NavLink>
    );
  };

  // ── Sidebar inner content ─────────────────────────────────
  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo + collapse toggle */}
      <div className="flex items-center h-14 border-b border-slate-800 px-3 bg-slate-900 flex-shrink-0">
        <div className={`flex items-center ${collapsed ? "justify-center w-full" : "flex-1 min-w-0"}`}>
          <ZeniPostLogo size={28} variant="animated" showText={!collapsed} />
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden md:flex items-center justify-center w-7 h-7 rounded-md text-slate-400 hover:text-white hover:bg-slate-700 transition-colors flex-shrink-0"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className="text-xs">{collapsed ? "→" : "←"}</span>
        </button>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3" aria-label="Main navigation">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className={`relative ${collapsed ? "px-2" : "px-3"} mb-1`}>
            {!collapsed && (
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-3 pt-3 pb-1">
                {group.label}
              </p>
            )}
            {collapsed && <div className="border-t border-gray-700 my-2" />}
            <div className="space-y-0.5 relative">
              {group.items.map((item) => (
                <NavItem key={item.to} item={item} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User section */}
      <div className="flex-shrink-0 border-t border-gray-200 p-3">
        {collapsed ? (
          <div className="flex flex-col items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${getAvatarColor(user?.name)}`}>
              {avatarLetter}
            </div>
            <button
              onClick={handleLogout}
              className="w-8 h-8 flex items-center justify-center rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
              title="Sign out"
            >
              <span className="text-sm">→</span>
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50">
              <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-medium ${getAvatarColor(user?.name)}`}>
                {avatarLetter}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{displayName}</p>
                <p className="text-xs text-gray-400 truncate">{user?.email || ""}</p>
              </div>
            </div>
            
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 w-full px-2 py-1.5 rounded-lg text-xs text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors"
            >
              <span>→</span>
              <span>Sign out</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 bg-slate-900 text-white rounded-lg shadow-lg"
        aria-label={mobileOpen ? "Close menu" : "Open menu"}
      >
        <span className="text-sm leading-none">{mobileOpen ? "✕" : "☰"}</span>
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={[
          "fixed top-0 left-0 z-40 h-screen bg-white shadow-xl",
          "transition-all duration-300 ease-in-out flex-shrink-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "md:translate-x-0",
          collapsed ? "md:w-16" : "md:w-60",
          "w-60",
        ].join(" ")}
        aria-label="Sidebar navigation"
      >
        <SidebarContent />
      </aside>

      {/* Desktop spacer */}
      <div
        className={[
          "hidden md:block flex-shrink-0 transition-all duration-300",
          collapsed ? "w-16" : "w-60",
        ].join(" ")}
        aria-hidden="true"
      />
    </>
  );
}