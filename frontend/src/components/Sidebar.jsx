// frontend/src/components/Sidebar.jsx
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import API from '../api';
import ZeniPostLogo from './ZeniPostLogo';

export default function Sidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  // ✅ User state
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const res = await API.get('/auth/me');
        setUser(res.data);
      } catch (err) {
        console.error('Failed to fetch user in sidebar:', err);
        if (err.response?.status === 401) {
          localStorage.removeItem('token');
          navigate('/login');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, [navigate]);

  // Navigation items
  const navigationItems = [
    { to: '/', label: 'Dashboard', icon: '🏠', description: 'Overview & Stats' },
    { to: '/analytics', label: 'Analytics', icon: '📊', description: 'Reports & Insights' },
    { to: '/subscribers', label: 'Subscribers', icon: '👥', description: 'Manage Contacts' },
    { to: '/campaigns', label: 'Campaigns', icon: '📢', description: 'Email Campaigns' },
    { to: '/templates', label: 'Templates', icon: '📄', description: 'Email Templates' },
    { to: '/automation', label: 'Automation', icon: '🤖', description: 'Email Automation' },
    { to: '/ab-testing', label: 'A/B Testing', icon: '🧪', description: 'Test & Optimize' },
    { to: '/segmentation', label: 'Segmentation', icon: '🎯', description: 'Target Groups' },
    { to: '/suppressions', label: 'Suppressions', icon: '🛡️', description: 'Blocked Emails' },
    { to: '/audit', label: 'Audit Trail', icon: '📋', description: 'Activity Logs' },
    { to: '/settings/email', label: 'Settings', icon: '⚙️', description: 'Configuration' }
  ];

  const navItem = (item) => {
    const isActive = pathname === item.to || (item.to !== '/' && pathname.startsWith(item.to));
    return (
      <NavLink
        key={item.to}
        to={item.to}
        className={({ isActive: navLinkActive }) =>
          `group flex items-center px-4 py-3 rounded-lg transition-all duration-200 ${
            navLinkActive || isActive
              ? 'bg-blue-100 text-blue-700 font-semibold shadow-sm border-l-4 border-blue-500'
              : 'hover:bg-gray-100 text-gray-700 hover:text-gray-900'
          }`
        }
        onClick={() => setIsMobileMenuOpen(false)}
      >
        <span className="text-lg mr-3">{item.icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">{item.label}</p>
          <p className="text-xs text-gray-500 truncate">{item.description}</p>
        </div>
        {isActive && <div className="w-2 h-2 bg-blue-500 rounded-full ml-2"></div>}
      </NavLink>
    );
  };

  const getAvatarColor = (name) => {
    if (!name) return "bg-gray-400";
    const first = name[0].toLowerCase();
    const colors = {
      a: "bg-red-500", b: "bg-orange-500", c: "bg-amber-500", d: "bg-yellow-500",
      e: "bg-lime-500", f: "bg-green-500", g: "bg-emerald-500", h: "bg-teal-500",
      i: "bg-cyan-500", j: "bg-sky-500", k: "bg-blue-500", l: "bg-indigo-500",
      m: "bg-violet-500", n: "bg-purple-500", o: "bg-fuchsia-500", p: "bg-pink-500",
      q: "bg-rose-500", r: "bg-red-600", s: "bg-orange-600", t: "bg-amber-600",
      u: "bg-yellow-600", v: "bg-green-600", w: "bg-blue-600", x: "bg-indigo-600",
      y: "bg-purple-600", z: "bg-pink-600"
    };
    return colors[first] || "bg-gray-500";
  };

  const isEditorPage = pathname.includes('/templates/create') || 
                       pathname.includes('/templates/edit') || 
                       pathname.includes('/campaigns/create') || 
                       pathname.includes('/campaigns/edit');

  if (isEditorPage) return null;

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-blue-800 text-white rounded-lg shadow-lg"
      >
        {isMobileMenuOpen ? <span className="text-lg">✕</span> : <span className="text-lg">☰</span>}
      </button>

      {/* Mobile Overlay */}
      {isMobileMenuOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black bg-opacity-50 z-30"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`
        ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
        md:translate-x-0
        fixed top-0 left-0 z-40
        w-64 bg-white shadow-xl
        h-screen flex flex-col
        transition-transform duration-300 ease-in-out
      `}>
        {/* Header with Animated Logo */}
          {/* Header with Animated Logo */}
<div className="h-24 flex items-center justify-center">
  <div className="flex items-center justify-center w-full h-full bg-gradient-to-r from-blue-800 to-blue-600">
    <ZeniPostLogo size={64} variant="animated" />
  </div>
</div>


        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
          {/* Main Navigation */}
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2">
              Main
            </h3>
            {navigationItems.slice(0, 5).map(navItem)}
          </div>

          {/* Content Management */}
          <div className="space-y-1 pt-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2">
              Content
            </h3>
            {navigationItems.slice(5, 9).map(navItem)}
          </div>

          {/* System */}
          <div className="space-y-1 pt-4">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2">
              System
            </h3>
            {navigationItems.slice(9).map(navItem)}
          </div>
        </nav>

        {/* User Info & Logout */}
        <div className="p-4 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center space-x-3 mb-4 p-3 bg-white rounded-lg border">
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${getAvatarColor(user?.name)}`}>
              {user?.name ? user.name.charAt(0).toUpperCase() : "?"}
            </div>

            <div className="flex-1 min-w-0">
              {loading ? (
                <>
                  <p className="text-sm font-medium text-gray-500">Loading...</p>
                  <p className="text-xs text-gray-400">...</p>
                </>
              ) : (
                <>
                  <p className="text-sm font-medium text-gray-900">
                    {user?.name ? `${user.name.charAt(0).toUpperCase()}${user.name.slice(1)}` : "Unknown User"}
                  </p>
                  <p className="text-xs text-gray-500 truncate">
                    {user?.email || "no-email"}
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            className="w-full bg-red-600 text-white px-4 py-3 rounded-lg hover:bg-red-700 transition-colors flex items-center justify-center gap-2 font-medium"
          >
            <span className="text-lg">🚪</span>
            Logout
          </button>
        </div>
      </div>

      {/* Main Content Spacer for Desktop */}
      <div className="hidden md:block w-64 flex-shrink-0"></div>
    </>
  );
}

