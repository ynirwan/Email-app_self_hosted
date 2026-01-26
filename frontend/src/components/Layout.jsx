import { useLocation, Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  const { pathname } = useLocation();
  const isEditorPage = pathname.includes('/templates/') || 
                       pathname.includes('/automation/create') || 
                       pathname.includes('/automation/edit');

  return (
    <div className="min-h-screen bg-gray-50 flex overflow-x-hidden">
      <Sidebar />
      <div className="flex-1 min-h-screen flex flex-col">
        <main className={`flex-1 ${isEditorPage ? 'p-0' : 'p-6 md:p-10'}`}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

