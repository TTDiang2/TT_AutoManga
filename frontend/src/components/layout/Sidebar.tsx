import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import type { TabId } from '../../types';
import { 
  FiFileText, 
  FiEdit3, 
  FiImage, 
  FiLayers, 
  FiGrid, 
  FiSettings,
  FiUser 
} from 'react-icons/fi';

const tabs: { id: TabId; icon: React.ReactNode }[] = [
  { id: 'storyboard', icon: <FiFileText size={20} /> },
  { id: 'characters', icon: <FiUser size={20} /> },
  { id: 'prompt', icon: <FiEdit3 size={20} /> },
  { id: 'assets', icon: <FiImage size={20} /> },
  { id: 'composer', icon: <FiLayers size={20} /> },
  { id: 'showcase', icon: <FiGrid size={20} /> },
  { id: 'settings', icon: <FiSettings size={20} /> },
];

export function Sidebar() {
  const { activeTab, setActiveTab } = useProjectStore();
  const { t } = useTranslation();

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">AM</div>
      <nav className="sidebar-nav">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span className="nav-tooltip">{t.tabs[tab.id]}</span>
          </div>
        ))}
      </nav>
    </aside>
  );
}
