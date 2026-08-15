import { useEffect } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { StoryboardTab } from './components/storyboard/StoryboardTab';
import { PromptLabTab } from './components/prompt/PromptLabTab';
import { AssetTab } from './components/assets/AssetTab';
import { ComposerTab } from './components/composer/ComposerTab';
import { ShowcaseTab } from './components/showcase/ShowcaseTab';
import { SettingsTab } from './components/settings/SettingsTab';
import { CharacterTab } from './components/characters/CharacterTab';
import { useProjectStore } from './store/projectStore';
import { useTranslation } from './hooks/useTranslation';
import './styles/globals.css';

function App() {
  const { activeTab, setSettings } = useProjectStore();
  const { t } = useTranslation();

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
      default:
        return <StoryboardTab />;
    }
  };

  const title = t.tabs[activeTab];
  const descriptions: Record<string, string> = {
    storyboard: t.storyboard.description,
    prompt: t.prompt.description,
    assets: t.assets.description,
    composer: t.composer.description,
    showcase: t.showcase.description,
    settings: t.settings.description,
    characters: t.characters.description,
  };
  const description = descriptions[activeTab] || t.storyboard.description;

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <header className="content-header">
          <h1>{title}</h1>
          <p>{description}</p>
        </header>
        <div className="content-body animate-fadeIn" key={activeTab}>
          {renderTab()}
        </div>
      </main>
    </div>
  );
}

export default App;
