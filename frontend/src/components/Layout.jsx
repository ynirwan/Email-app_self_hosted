import { useLocation, Outlet, NavLink } from "react-router-dom";
import Sidebar from "./Sidebar";
import { UserProvider } from "../contexts/UserContext";

// page title map — used in the topbar breadcrumb
const PAGE_TITLES = {
  "/": { title: "Dashboard", icon: "🏠" },
  "/analytics": { title: "Analytics", icon: "📊" },
  "/subscribers": { title: "Subscribers", icon: "👥" },
  "/segmentation": { title: "Segments", icon: "🎯" },
  "/suppressions": { title: "Suppressions", icon: "🛡️" },
  "/campaigns": { title: "Campaigns", icon: "📢" },
  "/campaigns/create": { title: "Create Campaign", icon: "✨" },
  "/templates": { title: "Templates", icon: "📄" },
  "/automation": { title: "Automation", icon: "🤖" },
  "/ab-testing": { title: "A/B Testing", icon: "⚖️ " },
  "/ab-testing/create": { title: "Create A/B Test", icon: "⚖️ " },
  "/audit": { title: "Audit Trail", icon: "📋" },
  "/settings": { title: "Settings", icon: "⚙️" },
  "/settings/email": { title: "Email Settings", icon: "⚙️" },
  "/settings/domain": { title: "Domain Settings", icon: "🌐" },
  "/settings/user": { title: "User Settings", icon: "👤" },
};

const isEditorRoute = (path) =>
  path.includes("/templates/") ||
  path.includes("/automation/create") ||
  path.includes("/automation/edit");

function getPageMeta(pathname) {
  // exact match first
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  // prefix match (longest wins)
  const match = Object.keys(PAGE_TITLES)
    .filter((k) => k !== "/" && pathname.startsWith(k))
    .sort((a, b) => b.length - a.length)[0];
  return match ? PAGE_TITLES[match] : { title: "ZeniPost", icon: "📧" };
}

function Topbar({ pathname }) {
  const meta = getPageMeta(pathname);

  return (
    <header className="h-14 flex-shrink-0 bg-white border-b border-gray-200 flex items-center px-4 md:px-6 gap-3">
      {/* page identity */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className="text-lg">{meta.icon}</span>
        <h1 className="text-base font-semibold text-gray-900 truncate">
          {meta.title}
        </h1>
      </div>

      {/* right side actions */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {/* quick-nav shortcuts — only shown on dashboard */}
        {pathname === "/" && (
          <div className="hidden sm:flex items-center gap-1">
            <NavLink
              to="/campaigns/create"
              className="px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              + New Campaign
            </NavLink>
          </div>
        )}

        {/* settings cog shortcut */}
        <NavLink
          to="/settings/email"
          className={({ isActive }) =>
            `w-8 h-8 flex items-center justify-center rounded-lg text-sm transition-colors ${
              isActive
                ? "bg-gray-100 text-gray-900"
                : "text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            }`
          }
          title="Settings"
        >
          ⚙️
        </NavLink>
      </div>
    </header>
  );
}

export default function Layout() {
  const { pathname } = useLocation();
  const isEditor = isEditorRoute(pathname);

  return (
    <UserProvider>
      <div className="min-h-screen bg-gray-50 flex">
        <Sidebar />

        {/* right panel */}
        <div className="flex-1 min-w-0 flex flex-col min-h-screen">
          {!isEditor && <Topbar pathname={pathname} />}
          <main
            className={`flex-1 min-w-0 overflow-auto ${isEditor ? "" : "p-4 md:p-8"}`}
          >
            <Outlet />
          </main>
        </div>
      </div>
    </UserProvider>
  );
}
