import { useEffect, useState } from 'react';
import { FiHelpCircle } from 'react-icons/fi';
import { Sidebar } from './components/layout/Sidebar';
import { StoryboardTab } from './components/storyboard/StoryboardTab';
import { PromptLabTab } from './components/prompt/PromptLabTab';
import { AssetTab } from './components/assets/AssetTab';
import { ComposerTab } from './components/composer/ComposerTab';
import { ShowcaseTab } from './components/showcase/ShowcaseTab';
import { SettingsTab } from './components/settings/SettingsTab';
import { CharacterTab } from './components/characters/CharacterTab';
import { ComicsTab } from './components/comics/ComicsTab';
import { WizardTab } from './components/wizard/WizardTab';
import { Tour } from './components/tour/Tour';
import { hasTour, isSeen } from './components/tour/tourLogic';
import { TooltipLayer } from './components/tooltip/TooltipLayer';
import { useTips } from './hooks/useTips';
import { useProjectStore } from './store/projectStore';
import { useTranslation } from './hooks/useTranslation';
import './styles/globals.css';

function App() {
  const activeTab = useProjectStore(s => s.activeTab);
  const setSettings = useProjectStore(s => s.setSettings);
  const { t } = useTranslation();
  const tip = useTips();
  // the tab whose tour is open; a tab's tour starts by itself on its first visit
  const [tourTab, setTourTab] = useState<string | null>(null);

  useEffect(() => {
    if (!hasTour(activeTab) || isSeen(activeTab)) return;
    // let the tab render (and fetch its lists) before pointing at things
    const id = window.setTimeout(() => setTourTab(activeTab), 700);
    return () => window.clearTimeout(id);
  }, [activeTab]);

  // the server's lettering fonts (data/fonts), so the Composer draws text the way the export does
  useEffect(() => {
    fetch('/api/fonts')
      .then(res => res.json())
      .then((data: { fonts: { family: string; url: string }[] }) => {
        const css = data.fonts.map(f => `@font-face { font-family: "${f.family}"; src: url("${f.url}"); }`).join('\n');
        if (!css) return;
        const style = document.createElement('style');
        style.dataset.userFonts = '';
        style.textContent = css;
        document.head.appendChild(style);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    fetch('/api/settings/')
      .then(res => res.json())
      .then(data => {
        setSettings({
          api: data.api,
          swarmui: data.swarmui,
          defaults: data.defaults,
          language: data.language || 'en',
        });
      })
      .catch(console.error);
  }, [setSettings]);

  const renderTab = () => {
    switch (activeTab) {
      case 'wizard':
        return <WizardTab />;
      case 'storyboard':
        return <StoryboardTab />;
      case 'prompt':
        return <PromptLabTab />;
      case 'assets':
        return <AssetTab />;
      case 'composer':
        return <ComposerTab />;
      case 'showcase':
        return <ShowcaseTab />;
      case 'settings':
        return <SettingsTab />;
      case 'characters':
        return <CharacterTab />;
      case 'comics':
        return <ComicsTab />;
      default:
        return <StoryboardTab />;
    }
  };

  const title = t.tabs[activeTab];
  const descriptions: Record<string, string> = {
    wizard: t.wizard.description,
    storyboard: t.storyboard.description,
    prompt: t.prompt.description,
    assets: t.assets.description,
    composer: t.composer.description,
    showcase: t.showcase.description,
    settings: t.settings.description,
    characters: t.characters.description,
    comics: t.comics.description,
  };
  const description = descriptions[activeTab] || t.storyboard.description;

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <header className="content-header">
          <div className="content-header-row">
            <div>
              <h1>{title}</h1>
              <p>{description}</p>
            </div>
            {hasTour(activeTab) && (
              <button type="button" className="btn btn-ghost tour-help" data-tip={tip.common.tour}
                onClick={() => setTourTab(activeTab)}>
                <FiHelpCircle size={16} /> {t.tour.button}
              </button>
            )}
          </div>
        </header>
        <div className="content-body animate-fadeIn" key={activeTab}>
          {renderTab()}
        </div>
      </main>
      <TooltipLayer />
      {tourTab === activeTab && hasTour(activeTab) && (
        <Tour key={activeTab} tab={activeTab} onClose={() => setTourTab(null)} />
      )}
    </div>
  );
}

export default App;
