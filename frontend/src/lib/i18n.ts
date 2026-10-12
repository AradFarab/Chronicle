/**
 * Translations for the PWA. Source strings are English (like the server) and are extracted
 * into backend/chronicle/locale/main.pot; the catalog comes from /api/translations/<language>.
 */
let messages: Record<string, string> = {}

export function setMessages(value: Record<string, string>): void {
  messages = value
}

export function __(text: string, replace?: (string | number)[], context?: string): string {
  let translated = (context && messages[`${text}:${context}`]) || messages[text] || text
  if (replace) {
    translated = translated.replace(/\{(\d+)\}/g, (match, index) =>
      replace[Number(index)] !== undefined ? String(replace[Number(index)]) : match
    )
  }
  return translated
}
