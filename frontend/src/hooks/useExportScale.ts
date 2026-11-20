import { useProjectStore } from '../store/projectStore';

/** Settings → Defaults → Export Quality, as a render scale of the 600×900 page. */
export const EXPORT_SCALES = { standard: 1, high: 2, print: 4 } as const;
export type ExportQuality = keyof typeof EXPORT_SCALES;

/** Unknown or missing values fall back to "high" (2×), the long-standing default. */
export function scaleForQuality(quality: string | undefined | null): number {
  return EXPORT_SCALES[quality as ExportQuality] ?? EXPORT_SCALES.high;
}

/** The render scale every export uses, from the saved Export Quality. */
export function useExportScale(): number {
  return useProjectStore(s => scaleForQuality(s.settings.defaults?.exportQuality));
}
