import { useLocation } from 'react-router-dom';

export default function MainLayout({ children }) {
  const location = useLocation();
  
  const isEditorPage = location.pathname.includes('/templates/') || 
                       location.pathname.includes('/automation/create') || 
                       location.pathname.includes('/automation/edit');

  // Pages that should have sidebar spacing
  const pagesWithSidebar = ['/campaigns', '/analytics', '/subscribers', '/templates', '/automation', '/ab-testing', '/segmentation', '/suppressions', '/audit', '/settings'];
  const needsSidebarSpacing = !isEditorPage && pagesWithSidebar.some(path => 
    location.pathname.startsWith(path)
  );

  return (
    <div className={needsSidebarSpacing ? 'ml-64' : ''}>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <div className="flex-1">
          {children}
        </div>
      </div>
    </div>
  );
}

