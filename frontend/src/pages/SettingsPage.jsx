// src/pages/SettingsPage.jsx
import React from 'react';
import { Link, useLocation, Outlet } from "react-router-dom";

export default function SettingsPage() {
  const location = useLocation();

  const tabs = [
    { name: "SMTP Settings", path: "/settings/email" },
    { name: "Domain Settings", path: "/settings/domain" },
  ];

  return (
    <div className="p-6">
      <div className="flex space-x-4 border-b mb-4">
        {tabs.map(tab => (
          <Link
            key={tab.path}
            to={tab.path}
            className={`px-4 py-2 ${
              location.pathname === tab.path
                ? "border-b-2 border-blue-500 font-semibold"
                : "text-gray-500 hover:text-blue-500"
            }`}
          >
            {tab.name}
          </Link>
        ))}
      </div>

      <Outlet /> {/* Renders the nested tab content */}
    </div>
  );
}

