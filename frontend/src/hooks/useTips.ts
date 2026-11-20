import { useProjectStore } from '../store/projectStore';
import { tips, type Tips } from '../i18n/tips';

/** Tooltip text in the current language: `data-tip={tip.storyboard.generate}`. */
export function useTips(): Tips {
  const language = useProjectStore((state) => state.settings.language) || 'en';
  return language === 'zh' ? tips.zh : tips.en;
}
