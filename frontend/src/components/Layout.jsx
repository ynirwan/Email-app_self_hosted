import { useLocation, Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  const { pathname } = useLocation();
  const isEditorPage = pathname.includes('/templates/create') || 
                       pathname.includes('/templates/edit') || 
                       pathname.includes('/campaigns/create') || 
                       pathname.includes('/campaigns/edit');

  return (
    <div className="min-h-screen bg-gray-50 flex overflow-x-hidden">
      <Sidebar />
      <div className="flex-1 min-h-screen">
        <main className={isEditorPage ? 'p-0' : 'p-6 md:p-8'}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

