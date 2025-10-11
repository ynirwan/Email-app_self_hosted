import { useLocation } from 'react-router-dom';

export default function MainLayout({ children }) {
  const location = useLocation();
  
  // Pages that should have sidebar spacing
  const pagesWithSidebar = ['/campaigns', '/analytics', '/subscribers', '/templates'];
  const needsSidebarSpacing = pagesWithSidebar.some(path => 
    location.pathname.startsWith(path)
  );

  return (
    <div className={needsSidebarSpacing ? 'ml-64' : ''}>
      <div className="min-h-screen bg-gray-50">
        {children}
      </div>
    </div>
  );
}

