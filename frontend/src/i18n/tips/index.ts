import common from './common';
import wizard from './wizard';
import storyboard from './storyboard';
import characters from './characters';
import prompt from './prompt';
import assets from './assets';
import composer from './composer';
import showcase from './showcase';
import comics from './comics';
import settings from './settings';

const files = { common, wizard, storyboard, characters, prompt, assets, composer, showcase, comics, settings };
type Files = typeof files;
export type Tips = { [K in keyof Files]: Files[K]['en'] };

function pick(lang: 'en' | 'zh'): Tips {
  return Object.fromEntries(Object.entries(files).map(([k, v]) => [k, v[lang]])) as Tips;
}

export const tips: Record<'en' | 'zh', Tips> = { en: pick('en'), zh: pick('zh') };
