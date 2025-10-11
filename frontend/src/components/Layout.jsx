// frontend/src/components/Layout.jsx
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar />
      <div className="ml-64 min-h-screen">
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

