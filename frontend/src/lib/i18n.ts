/**
 * Translations for the PWA. Source strings are English (like the rest of the app) and are
 * extracted into hozur/locale/main.pot; the user's language comes rendered into the page.
 */
let messages: Record<string, string> = window.hozur_messages ?? {}

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
