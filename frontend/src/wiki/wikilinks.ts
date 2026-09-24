const CATEGORY_ALIAS: Record<string, string> = {
  persons: 'person',
  lso: 'squad',
  projects: 'project',
  index: 'wiki',
}

/** Нормализованная категория по слагу ИЛИ bare-kind (frontmatter kind без `/`). */
export function categoryOf(slugOrKind: string): string {
  const head = slugOrKind.includes('/') ? slugOrKind.split('/')[0] : slugOrKind
  return CATEGORY_ALIAS[head] ?? head
}

/** Заголовок -> якорь: нижний регистр, пробелы в _, только буквы/цифры. */
export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/[\s\-–—]+/g, '_')
    .replace(/[^a-zа-яё0-9_]/g, '')
    .replace(/^_+|_+$/g, '')
}

export interface TocEntry {
  id: string
  text: string
}

const SERVICE_SECTION = 'источники данных'

/** ## -заголовки -> пункты содержания (служебный раздел пропущен). */
export function extractToc(body: string): TocEntry[] {
  const out: TocEntry[] = []
  for (const line of body.split('\n')) {
    const h = /^#{2,3}\s+(.*)$/.exec(line)
    if (!h) continue
    const text = h[1].trim()
    if (text.toLowerCase() === SERVICE_SECTION) continue
    out.push({ id: slugifyHeading(text), text })
  }
  return out
}

export interface InfoRow {
  k: string
  v: string
}

const META_BULLET = /^-\s+\*\*(.+?)\*\*\s*(.*)$/

/**
 * Ведущие «- **Ключ:** значение» (до первого ##) -> строки инфобокса.
 * Возвращает строки и тело без них.
 */
export function extractInfobox(body: string): { rows: InfoRow[]; rest: string } {
  const rows: InfoRow[] = []
  const kept: string[] = []
  let inMeta = true
  for (const line of body.split('\n')) {
    if (inMeta && /^##\s/.test(line)) inMeta = false
    if (inMeta) {
      const m = META_BULLET.exec(line)
      if (m) {
        rows.push({ k: m[1].replace(/:$/, ''), v: m[2].trim() })
        continue
      }
      if (line.trim() !== '') {
        // Не-мета до первого ## (обычно заголовок/текст) — оставляем, метабокс не начали
        if (rows.length === 0) {
          kept.push(line)
          continue
        }
        inMeta = false
      } else {
        if (rows.length === 0) {
          kept.push(line)
          continue
        }
        // пустая строка внутри метаблока — пропускаем, ждём ещё буллеты или ##
        continue
      }
    }
    kept.push(line)
  }
  return { rows, rest: kept.join('\n') }
}
