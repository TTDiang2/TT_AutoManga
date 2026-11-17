import { useProjectStore } from '../../store/projectStore';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme, type ThemeChoice } from '../../hooks/useTheme';
import type { TabId } from '../../types';
import { 
  FiFileText, 
  FiEdit3, 
  FiImage, 
  FiLayers, 
  FiGrid, 
  FiSettings,
  FiUser,
  FiBookOpen,
  FiMonitor,
  FiSun,
  FiMoon
} from 'react-icons/fi';

const tabs: { id: TabId; icon: React.ReactNode }[] = [
  { id: 'storyboard', icon: <FiFileText size={20} /> },
  { id: 'characters', icon: <FiUser size={20} /> },
  { id: 'prompt', icon: <FiEdit3 size={20} /> },
  { id: 'assets', icon: <FiImage size={20} /> },
  { id: 'composer', icon: <FiLayers size={20} /> },
  { id: 'showcase', icon: <FiGrid size={20} /> },
  { id: 'comics', icon: <FiBookOpen size={20} /> },
  { id: 'settings', icon: <FiSettings size={20} /> },
];

const THEMES: { id: ThemeChoice; label: string; icon: React.ReactNode }[] = [
  { id: 'system', label: 'Theme: system', icon: <FiMonitor size={18} /> },
  { id: 'light', label: 'Theme: light', icon: <FiSun size={18} /> },
  { id: 'dark', label: 'Theme: dark', icon: <FiMoon size={18} /> },
];

export function Sidebar() {
  const { activeTab, setActiveTab } = useProjectStore();
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const current = THEMES.find(x => x.id === theme) || THEMES[0];
  const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];

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
      <button
        className="nav-item sidebar-theme"
        onClick={() => setTheme(next.id)}
        aria-label={`${current.label} (switch to ${next.id})`}
      >
        {current.icon}
        <span className="nav-tooltip">{current.label}</span>
      </button>
    </aside>
  );
}
