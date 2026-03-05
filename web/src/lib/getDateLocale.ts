/**
 * Date locale for Intl (zh-CN, zh-TW, en-US).
 * Separate module so bundlers reliably resolve the export.
 */
export function getDateLocale(language?: string | null): string {
  if (language === 'zh') return 'zh-CN';
  if (language === 'zh-TW') return 'zh-TW';
  return 'en-US';
}
