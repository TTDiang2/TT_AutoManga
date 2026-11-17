import { useProjectStore } from '../store/projectStore';
import { translations } from '../i18n';
import type { TranslationKeys } from '../i18n';

export function useTranslation() {
  const language = useProjectStore((state) => state.settings.language) || 'en';
  
  const t = translations[language as keyof typeof translations] as TranslationKeys;
  
  return {
    t,
    language,
  };
}

/** Fills {name} placeholders in a translated string: fill(t.prompt.allFailed, { n: 3 }). */
export function fill(text: string, values: Record<string, string | number>) {
  return text.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m));
}
