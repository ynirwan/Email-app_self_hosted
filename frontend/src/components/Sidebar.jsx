import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useUser } from "../contexts/UserContext";
import ZeniPostLogo from "./ZeniPostLogo";

// Nav groups — logical grouping, campaigns with subscribers not automation
const NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      {
        to: "/",
        label: "Dashboard",
        icon: "🏠",
        description: "Overview & stats",
      },
      {
        to: "/analytics",
        label: "Analytics",
        icon: "📊",
        description: "Reports & insights",
      },
    ],
  },
  {
    label: "Audience",
    items: [
      {
        to: "/subscribers",
        label: "Subscribers",
        icon: "👥",
        description: "Manage contacts",
      },
      {
        to: "/segmentation",
        label: "Segments",
        icon: "🎯",
        description: "Target groups",
      },
      {
        to: "/suppressions",
        label: "Suppressions",
        icon: "🛡️",
        description: "Blocked emails",
      },
    ],
  },
  {
    label: "Sending",
    items: [
      {
        to: "/campaigns",
        label: "Campaigns",
        icon: "📢",
        description: "Email campaigns",
      },
      {
        to: "/templates",
        label: "Templates",
        icon: "📄",
        description: "Email templates",
      },
      {
        to: "/ab-testing",
        label: "A/B Testing",
        icon: "⚖️ ",
        description: "Test & optimise",
      },
      {
        to: "/automation",
        label: "Automation",
        icon: "🤖",
        description: "Email sequences",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        to: "/audit",
        label: "Audit Trail",
        icon: "📋",
        description: "Activity logs",
      },
      {
        to: "/settings/email",
        label: "Settings",
        icon: "⚙️",
        description: "Configuration",
      },
    ],
  },
];

function getAvatarColor(name) {
  if (!name) return "bg-gray-400";
  const colors = [
    "bg-blue-500",
    "bg-violet-500",
    "bg-emerald-500",
    "bg-amber-500",
    "bg-rose-500",
    "bg-cyan-500",
    "bg-indigo-500",
    "bg-teal-500",
  ];
  return colors[name.charCodeAt(0) % colors.length];
}

export default function Sidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, userLoading } = useUser();

  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  const avatarLetter = user?.name ? user.name.charAt(0).toUpperCase() : "?";
  const displayName = user?.name
    ? user.name.charAt(0).toUpperCase() + user.name.slice(1)
    : "Unknown";

  // ── Single NavItem ─────────────────────────────────────────
  const NavItem = ({ item }) => {
    const isActive =
      pathname === item.to || (item.to !== "/" && pathname.startsWith(item.to));

    return (
      <NavLink
        to={item.to}
        title={collapsed ? item.label : undefined}
        aria-label={item.label}
        onClick={() => setMobileOpen(false)}
        className={({ isActive: navActive }) => {
          const active = navActive || isActive;
          return [
            "flex items-center rounded-lg transition-all duration-150 group",
            collapsed ? "justify-center px-2 py-2.5" : "px-3 py-2.5",
            active
              ? "bg-blue-50 text-blue-700"
              : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
          ].join(" ");
        }}
      >
        {({ isActive: navActive }) => {
          const active = navActive || isActive;
          return (
            <>
              {/* Active bar on left edge */}
              <span
                className={[
                  "absolute left-0 w-0.5 h-5 rounded-r-full transition-all",
                  active ? "bg-blue-100" : "bg-transparent",
                ].join(" ")}
              />

              <span
                className={`text-base flex-shrink-0 ${collapsed ? "" : "mr-3"}`}
              >
                {item.icon}
              </span>

              {!collapsed && (
                <div className="flex-1 min-w-0 overflow-hidden">
                  <p
                    className={`text-sm font-medium leading-none truncate ${active ? "text-blue-700" : ""}`}
                  >
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

  // ── Sidebar inner content (shared between mobile & desktop) ─
  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo + collapse toggle */}
      <div className="flex items-center h-14 border-b border-slate-800 px-3 bg-slate-900 flex-shrink-0">
        <div
          className={`flex items-center ${collapsed ? "justify-center w-full" : "flex-1 min-w-0"}`}
        >
          <ZeniPostLogo size={28} variant="animated" />
          {!collapsed && (
            <span className="ml-2 text-white font-bold text-sm truncate">
              
            </span>
          )}
        </div>
        {/* Collapse toggle — desktop only */}
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
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden py-3"
        aria-label="Main navigation"
      >
        {NAV_GROUPS.map((group) => (
          <div
            key={group.label}
            className={`relative ${collapsed ? "px-2" : "px-3"} mb-1`}
          >
            {/* Group label — hidden when collapsed */}
            {!collapsed && (
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-3 pt-3 pb-1">
                {group.label}
              </p>
            )}
            {collapsed && <div className="border-t border-gray-200 my-2" />}
            <div className="space-y-0.5 relative">
              {group.items.map((item) => (
                <NavItem key={item.to} item={item} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User section + logout */}
      <div className="flex-shrink-0 border-t border-gray-200 p-3">
        {collapsed ? (
          // Collapsed: just avatar + logout icon stacked
          <div className="flex flex-col items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold ${getAvatarColor(user?.name)}`}
              title={displayName}
            >
              {avatarLetter}
            </div>
            <button
              onClick={handleLogout}
              title="Logout"
              aria-label="Logout"
              className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            >
              <span className="text-sm">🚪</span>
            </button>
          </div>
        ) : (
          // Expanded: avatar row + logout button
          <div className="space-y-2">
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg bg-gray-50 border border-gray-100">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0 ${getAvatarColor(user?.name)}`}
              >
                {avatarLetter}
              </div>
              <div className="flex-1 min-w-0">
                {userLoading ? (
                  <div className="h-3 bg-gray-200 rounded animate-pulse w-20 mb-1" />
                ) : (
                  <>
                    <p className="text-xs font-semibold text-gray-800 truncate">
                      {displayName}
                    </p>
                    <p className="text-xs text-gray-400 truncate">
                      {user?.email || ""}
                    </p>
                  </>
                )}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 border border-gray-200 hover:border-red-200 transition-colors"
            >
              <span className="text-sm">🚪</span>
              Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* ── Mobile hamburger ── */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="md:hidden fixed top-3.5 left-4 z-50 p-2 bg-slate-900 text-white rounded-lg shadow-lg"
        aria-label={mobileOpen ? "Close menu" : "Open menu"}
      >
        <span className="text-sm leading-none">{mobileOpen ? "✕" : "☰"}</span>
      </button>

      {/* ── Mobile overlay ── */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar panel ── */}
      <aside
        className={[
          "fixed top-0 left-0 z-40 h-screen bg-white shadow-xl",
          "transition-all duration-300 ease-in-out flex-shrink-0",
          // mobile: slide in/out
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // desktop: always visible, width switches
          "md:translate-x-0",
          collapsed ? "md:w-16" : "md:w-60",
          // mobile always full width sidebar
          "w-60",
        ].join(" ")}
        aria-label="Sidebar navigation"
      >
        <SidebarContent />
      </aside>

      {/* ── Desktop spacer — keeps main content pushed right ── */}
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
