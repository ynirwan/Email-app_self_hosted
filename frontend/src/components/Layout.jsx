import { useLocation, Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  const { pathname } = useLocation();
  const isTemplateCreation = pathname.includes('/templates/create') || pathname.includes('/templates/edit');

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <Sidebar />
      <div className={`flex-1 min-h-screen ${isTemplateCreation ? 'ml-0' : ''}`}>
        <main className={isTemplateCreation ? 'p-0' : 'p-8'}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

