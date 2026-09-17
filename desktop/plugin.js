import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  SIDEBAR_NAV_AREA,
  Skeleton,
  Textarea,
  host,
  useMutation,
  usePluginI18n,
  useQuery
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'

const VERSION = '0.6.2'
const PLUGIN_ID = 'hermes-memory-ui'
const PLUGIN_NAME = 'Hermes Memory UI'
const PLUGIN_ROUTE = '/memory'
const PROVIDER_KEYS = ['holographic', 'mem0', 'honcho', 'mnemosyne', 'hindsight', 'byterover']
const MUTED = { color: 'var(--ui-text-secondary)' }
const BORDER = { borderColor: 'var(--ui-stroke-secondary)' }
export const QUERY_CONTROL_CONFIG = {
  snapshot: {
    defaultLimit: 500,
    limitOptions: [10, 25, 50, 100, 500, 1000, 2000]
  },
  hindsight: {
    defaultLimit: 25,
    limitOptions: [10, 25, 50, 100]
  },
  mnemosyne: {
    defaultLimit: 25,
    defaultTemporalWeight: 0.2,
    limitOptions: [10, 25, 50, 100],
    temporalWeightOptions: [0, 0.2, 0.5, 0.8, 1]
  },
  byterover: {
    queryTimeout: 60
  },
  session: {
    defaultLimit: 3,
    defaultSort: 'newest',
    sortOptions: ['newest', 'oldest']
  }
}

function Card({ className = '', children }) {
  return jsx('section', {
    className: `rounded-md border ${className}`,
    style: BORDER,
    children
  })
}

function CardHeader({ className = '', children }) {
  return jsx('header', { className: `p-4 ${className}`, children })
}

function CardContent({ className = '', children }) {
  return jsx('div', { className: `px-4 pb-4 ${className}`, children })
}

function CardTitle({ className = '', children }) {
  return jsx('h4', { className: `font-semibold ${className}`, children })
}

const bundles = {
  en: {
    title: 'Memory',
    openMemory: 'Open Memory',
    subtitle: 'A read-only overview of the memory Hermes can use in this profile.',
    refresh: 'Apply / refresh',
    filters: 'Memory filters',
    filterHint: 'Search and limit apply across providers; category and trust apply to Holographic facts.',
    search: 'Search',
    searchPlaceholder: 'content, facts, or tags…',
    category: 'Category',
    allCategories: 'All categories',
    minTrust: 'Minimum trust',
    limit: 'Limit',
    loading: 'Loading memory…',
    searching: 'Searching…',
    failed: 'Unable to load memory',
    empty: 'Nothing to show',
    builtin: 'Built-in memory',
    builtinHint: 'The active profile files Hermes reads directly.',
    providers: 'Configured providers',
    providerHint: 'Read-only provider state and visible memory collections.',
    sessions: 'Session search',
    sessionHint: 'Search previous Hermes sessions without changing memory state.',
    source: 'Source',
    sortOrder: 'Sort order',
    newest: 'Newest',
    oldest: 'Oldest',
    runSearch: 'Search sessions',
    query: 'Query',
    queryContentFilter: 'Query / content filter',
    queryContentPlaceholder: 'ask or filter provider memory…',
    queryHint: 'Operations run only when you choose an action.',
    temporalWeight: 'Temporal weight',
    loadContents: 'Load contents',
    recall: 'Recall',
    reflect: 'Reflect',
    prefetch: 'Preview prefetch',
    byteRover: 'Ask ByteRover',
    noProviders: 'No optional memory provider is configured.',
    operationFailed: 'The requested read-only operation failed.',
    operationEmpty: 'Run an operation to see its result.',
    readOnly: 'Read-only',
    configured: 'Configured',
    available: 'Available',
    unavailable: 'Unavailable',
    result: 'Result',
    contents: 'Contents',
    overview: 'Overview',
    totalEntries: 'Built-in entries',
    activeProviders: 'Active providers',
    holographicFacts: 'Holographic facts',
    lastSnapshot: 'Snapshot updated',
    entries: 'Entries',
    modified: 'Modified',
    filePath: 'File path',
    characterUsage: 'Character usage',
    facts: 'Facts',
    shown: 'Shown',
    entities: 'Entities',
    banks: 'Banks',
    retrieved: 'Retrieved',
    helpful: 'Helpful',
    created: 'Created',
    updated: 'Updated',
    trust: 'Trust',
    tags: 'Tags',
    status: 'Status',
    memories: 'Memories',
    conclusions: 'Conclusions',
    cardFacts: 'Card facts',
    representation: 'Representation',
    userPeer: 'User peer',
    aiPeer: 'AI peer',
    results: 'Results',
    noMatches: 'No items match the current filters.',
    noFacts: 'No Holographic facts match the current filters.',
    noDatabase: 'The Holographic database does not exist yet.',
    noEntries: 'This memory file has no entries yet.',
    noSessions: 'No matching sessions found.',
    session: 'Session',
    messages: 'Matching context',
    reflection: 'Reflection',
    context: 'Context',
    metadata: 'Metadata',
    details: 'Details',
    yes: 'Yes',
    no: 'No',
    unknown: '—',
    allSources: 'All sources',
    entryCount: count => `${count} ${count === 1 ? 'entry' : 'entries'}`,
    itemCount: count => `${count} ${count === 1 ? 'item' : 'items'}`,
    storeNumber: number => `Store ${number}`,
    charsUsed: (used, maximum) => `${used} / ${maximum} characters`,
    percentUsed: value => `${value}% used`,
    factNumber: value => `Fact #${value}`,
    resultNumber: value => `Result #${value}`
  },
  pl: {
    title: 'Pamięć',
    openMemory: 'Otwórz pamięć',
    subtitle: 'Przegląd pamięci dostępnej dla Hermes w tym profilu — tylko do odczytu.',
    refresh: 'Zastosuj / odśwież',
    filters: 'Filtry pamięci',
    filterHint: 'Wyszukiwanie i limit dotyczą wszystkich źródeł; kategoria i zaufanie dotyczą faktów Holographic.',
    search: 'Szukaj',
    searchPlaceholder: 'treść, fakty lub tagi…',
    category: 'Kategoria',
    allCategories: 'Wszystkie kategorie',
    minTrust: 'Minimalne zaufanie',
    limit: 'Limit',
    loading: 'Wczytywanie pamięci…',
    searching: 'Wyszukiwanie…',
    failed: 'Nie można wczytać pamięci',
    empty: 'Brak danych do pokazania',
    builtin: 'Wbudowana pamięć',
    builtinHint: 'Pliki aktywnego profilu odczytywane bezpośrednio przez Hermes.',
    providers: 'Skonfigurowane źródła',
    providerHint: 'Stan źródeł i widoczne kolekcje pamięci — tylko do odczytu.',
    sessions: 'Wyszukiwanie sesji',
    sessionHint: 'Przeszukuj poprzednie sesje Hermes bez zmieniania pamięci.',
    source: 'Źródło',
    sortOrder: 'Kolejność',
    newest: 'Najnowsze',
    oldest: 'Najstarsze',
    runSearch: 'Szukaj sesji',
    query: 'Zapytanie',
    queryContentFilter: 'Zapytanie / filtr zawartości',
    queryContentPlaceholder: 'zapytaj lub filtruj pamięć źródła…',
    queryHint: 'Operacje uruchamiają się wyłącznie po wybraniu działania.',
    temporalWeight: 'Waga czasowa',
    loadContents: 'Wczytaj zawartość',
    recall: 'Wyszukaj w pamięci',
    reflect: 'Podsumuj pamięć',
    prefetch: 'Podgląd kontekstu',
    byteRover: 'Zapytaj ByteRover',
    noProviders: 'Nie skonfigurowano opcjonalnego dostawcy pamięci.',
    operationFailed: 'Żądana operacja tylko do odczytu nie powiodła się.',
    operationEmpty: 'Uruchom operację, aby zobaczyć wynik.',
    readOnly: 'Tylko do odczytu',
    configured: 'Skonfigurowane',
    available: 'Dostępne',
    unavailable: 'Niedostępne',
    result: 'Wynik',
    contents: 'Zawartość',
    overview: 'Przegląd',
    totalEntries: 'Wbudowane wpisy',
    activeProviders: 'Aktywne źródła',
    holographicFacts: 'Fakty Holographic',
    lastSnapshot: 'Aktualizacja widoku',
    entries: 'Wpisy',
    modified: 'Zmodyfikowano',
    filePath: 'Ścieżka pliku',
    characterUsage: 'Użycie znaków',
    facts: 'Fakty',
    shown: 'Pokazano',
    entities: 'Encje',
    banks: 'Banki',
    retrieved: 'Odczytano',
    helpful: 'Pomocne',
    created: 'Utworzono',
    updated: 'Zaktualizowano',
    trust: 'Zaufanie',
    tags: 'Tagi',
    status: 'Stan',
    memories: 'Wspomnienia',
    conclusions: 'Wnioski',
    cardFacts: 'Fakty profilu',
    representation: 'Reprezentacja',
    userPeer: 'Profil użytkownika',
    aiPeer: 'Profil AI',
    results: 'Wyniki',
    noMatches: 'Brak elementów pasujących do filtrów.',
    noFacts: 'Brak faktów Holographic pasujących do filtrów.',
    noDatabase: 'Baza Holographic jeszcze nie istnieje.',
    noEntries: 'Ten plik pamięci nie zawiera jeszcze wpisów.',
    noSessions: 'Nie znaleziono pasujących sesji.',
    session: 'Sesja',
    messages: 'Pasujący kontekst',
    reflection: 'Podsumowanie',
    context: 'Kontekst',
    metadata: 'Metadane',
    details: 'Szczegóły',
    yes: 'Tak',
    no: 'Nie',
    unknown: '—',
    allSources: 'Wszystkie źródła',
    entryCount: count => `${count} ${count === 1 ? 'wpis' : 'wpisów'}`,
    itemCount: count => `${count} ${count === 1 ? 'element' : 'elementów'}`,
    storeNumber: number => `Magazyn ${number}`,
    charsUsed: (used, maximum) => `${used} / ${maximum} znaków`,
    percentUsed: value => `Wykorzystano ${value}%`,
    factNumber: value => `Fakt #${value}`,
    resultNumber: value => `Wynik #${value}`
  }
}

function makePath(path, params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

function boundedNumber(value, fallback, minimum, maximum, integer = false) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  const bounded = Math.max(minimum, Math.min(maximum, parsed))
  return integer ? Math.trunc(bounded) : bounded
}

export function normalizeSnapshotFilters(filters = {}) {
  return {
    limit: boundedNumber(filters.limit, QUERY_CONTROL_CONFIG.snapshot.defaultLimit, 1, 2000, true),
    minTrust: boundedNumber(filters.minTrust ?? filters.min_trust, 0, 0, 1),
    category: String(filters.category || '').trim(),
    search: String(filters.search || '').trim()
  }
}

function selectedOption(value, options, fallback) {
  const parsed = Number(value)
  return options.includes(parsed) ? parsed : fallback
}

export function buildProviderOperationOptions(provider, kind, controls = {}) {
  const query = String(controls.query || '').trim()
  if (provider === 'hindsight') {
    const limit = selectedOption(
      controls.limit,
      QUERY_CONTROL_CONFIG.hindsight.limitOptions,
      QUERY_CONTROL_CONFIG.hindsight.defaultLimit
    )
    if (kind === 'contents') return { search: query, limit }
    if (kind === 'recall') return { query, limit }
    if (kind === 'reflect') return { query }
  }
  if (provider === 'mnemosyne') {
    const limit = selectedOption(
      controls.limit,
      QUERY_CONTROL_CONFIG.mnemosyne.limitOptions,
      QUERY_CONTROL_CONFIG.mnemosyne.defaultLimit
    )
    const temporalWeight = selectedOption(
      controls.temporalWeight,
      QUERY_CONTROL_CONFIG.mnemosyne.temporalWeightOptions,
      QUERY_CONTROL_CONFIG.mnemosyne.defaultTemporalWeight
    )
    if (kind === 'contents') return { search: query, limit }
    if (kind === 'recall') return { query, limit, temporalWeight }
    if (kind === 'prefetch') return { query }
  }
  throw new Error(`Unsupported ${provider} operation: ${kind}`)
}

export function createMemoryApi(ctx) {
  const get = (path, params, timeoutMs) => ctx.rest(makePath(path, params), { timeoutMs })
  return {
    getSnapshot: (filters = {}) => {
      const normalized = normalizeSnapshotFilters(filters)
      return get('/snapshot', {
        limit: normalized.limit,
        min_trust: normalized.minTrust,
        category: normalized.category,
        search: normalized.search
      }, 120_000)
    },
    searchSessions: options => get('/session-search', options, 60_000),
    queryByteRover: (query, timeout = QUERY_CONTROL_CONFIG.byterover.queryTimeout) => get(
      '/byterover/query',
      { query, timeout },
      Math.max(15_000, Number(timeout) * 1000 + 10_000)
    ),
    getHindsightContents: options => get('/hindsight/contents', options, 120_000),
    recallHindsight: (query, limit = QUERY_CONTROL_CONFIG.hindsight.defaultLimit) => get('/hindsight/recall', { query, limit }, 120_000),
    reflectHindsight: query => get('/hindsight/reflect', { query }, 180_000),
    getMnemosyneContents: options => get('/mnemosyne/contents', options, 120_000),
    recallMnemosyne: (
      query,
      limit = QUERY_CONTROL_CONFIG.mnemosyne.defaultLimit,
      temporalWeight = QUERY_CONTROL_CONFIG.mnemosyne.defaultTemporalWeight
    ) => get('/mnemosyne/recall', {
      query,
      limit,
      temporal_weight: temporalWeight
    }, 120_000),
    prefetchMnemosyne: query => get('/mnemosyne/prefetch', { query }, 120_000)
  }
}

export function visibleProviderKeys(snapshot) {
  return PROVIDER_KEYS.filter(key => snapshot?.[key]?.provider_configured === true)
}

function messageFor(error) {
  if (!error) return ''
  return error instanceof Error ? error.message : String(error)
}

function list(value) {
  return Array.isArray(value) ? value : []
}

function finite(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function display(value, t) {
  if (value === undefined || value === null || value === '') return t('unknown')
  if (typeof value === 'boolean') return value ? t('yes') : t('no')
  return String(value)
}

function formatTime(value, t) {
  if (value === undefined || value === null || value === '') return t('unknown')
  const numeric = Number(value)
  const date = typeof value === 'number' || (typeof value === 'string' && value.trim() && Number.isFinite(numeric))
    ? new Date(numeric < 1_000_000_000_000 ? numeric * 1000 : numeric)
    : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function humanize(key) {
  return String(key || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase())
}

function score(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(3) : null
}

function tagValues(value) {
  if (Array.isArray(value)) return value.filter(item => item !== null && item !== undefined).map(String)
  if (value && typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}: ${display(item, key => key)}`)
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch (_) {
    // Provider tag strings are also commonly comma-separated.
  }
  return value.split(',').map(item => item.trim()).filter(Boolean)
}

function Field({ label, children, className = '' }) {
  return jsxs('label', {
    className: `flex min-w-[9rem] flex-1 flex-col gap-1.5 ${className}`,
    children: [
      jsx('span', { className: 'text-xs font-medium', style: MUTED, children: label }),
      children
    ]
  })
}

function NativeSelect({ value, onValueChange, placeholder, options }) {
  return jsxs(Select, {
    value: String(value),
    onValueChange,
    children: [
      jsx(SelectTrigger, { children: jsx(SelectValue, { placeholder }) }),
      jsx(SelectContent, {
        children: options.map(option => jsx(SelectItem, {
          value: String(option.value),
          children: option.label
        }, String(option.value)))
      })
    ]
  })
}

function SectionHeading({ title, description, aside }) {
  return jsxs('div', {
    className: 'flex flex-wrap items-start justify-between gap-3',
    children: [
      jsxs('div', {
        className: 'min-w-0',
        children: [
          jsx('h3', { className: 'text-base font-semibold', children: title }),
          description ? jsx('p', { className: 'mt-1 text-sm', style: MUTED, children: description }) : null
        ]
      }),
      aside
    ]
  })
}

function StatCard({ label, value, hint }) {
  return jsx(Card, {
    className: 'h-full',
    children: jsx(CardContent, {
      className: 'flex h-full min-h-24 flex-col justify-center gap-1 p-4',
      children: jsxs(Fragment, {
        children: [
          jsx('span', { className: 'text-xs font-medium', style: MUTED, children: label }),
          jsx('strong', { className: 'truncate text-xl font-semibold', children: value }),
          hint ? jsx('span', { className: 'truncate text-xs', style: MUTED, children: hint }) : null
        ]
      })
    })
  })
}

function MetricGrid({ children }) {
  return jsx('div', {
    className: 'grid gap-3',
    style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 12rem), 1fr))' },
    children
  })
}

function PathRow({ label, value }) {
  if (!value) return null
  return jsxs('div', {
    className: 'flex min-w-0 items-start gap-2 rounded-md border px-3 py-2 text-xs',
    style: BORDER,
    children: [
      jsx('span', { className: 'shrink-0 font-medium', style: MUTED, children: label }),
      jsx('span', { className: 'min-w-0 break-all font-mono', children: String(value) })
    ]
  })
}

function UsageMeter({ value, label }) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  const percent = Math.max(0, Math.min(100, numeric))
  return jsxs('div', {
    className: 'space-y-1.5',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between gap-3 text-xs',
        style: MUTED,
        children: [
          jsx('span', { children: label }),
          jsx('span', { children: `${percent}%` })
        ]
      }),
      jsx('div', {
        className: 'h-1.5 overflow-hidden rounded-full',
        style: { backgroundColor: 'var(--ui-stroke-secondary)' },
        children: jsx('div', {
          className: 'h-full rounded-full',
          style: { backgroundColor: 'var(--ui-accent)', width: `${percent}%` }
        })
      })
    ]
  })
}

function InlineText({ value }) {
  const parts = String(value).split(/(`[^`\n]+`)/g)
  return jsx(Fragment, {
    children: parts.map((part, index) => part.startsWith('`') && part.endsWith('`')
      ? jsx('code', {
        className: 'font-mono',
        style: { color: 'var(--ui-text-secondary)', fontSize: '0.9em' },
        children: part.slice(1, -1)
      }, index)
      : part)
  })
}

function KeyValueGrid({ rows, t }) {
  const visible = rows.filter(row => row && row.value !== undefined && row.value !== null && row.value !== '')
  if (!visible.length) return null
  return jsx('dl', {
    className: 'grid gap-x-6 gap-y-3',
    style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 12rem), 1fr))' },
    children: visible.map((row, index) => jsxs('div', {
      className: 'min-w-0',
      children: [
        jsx('dt', { className: 'text-xs', style: MUTED, children: row.label }),
        jsx('dd', { className: 'mt-0.5 break-words text-sm font-medium', children: display(row.value, t) })
      ]
    }, row.label || index))
  })
}

function TagList({ value, label, t }) {
  const tags = tagValues(value)
  if (!tags.length) return null
  return jsxs('div', {
    className: 'mt-3 flex flex-wrap items-center gap-1.5',
    children: [
      label ? jsx('span', { className: 'mr-1 text-xs', style: MUTED, children: label }) : null,
      ...tags.slice(0, 24).map((tag, index) => jsx(Badge, { variant: 'outline', children: tag }, `${tag}-${index}`)),
      tags.length > 24 ? jsx(Badge, { variant: 'muted', children: `+${tags.length - 24}` }) : null
    ]
  })
}

function StructuredValue({ value, t, depth = 0 }) {
  if (value === undefined || value === null || value === '') {
    return jsx('span', { style: MUTED, children: t('unknown') })
  }
  if (typeof value !== 'object') {
    return jsx('span', { className: 'whitespace-pre-wrap break-words text-sm', children: display(value, t) })
  }
  if (depth >= 3) {
    const count = Array.isArray(value) ? value.length : Object.keys(value).length
    return jsx(Badge, { variant: 'outline', children: t('itemCount', count) })
  }
  if (Array.isArray(value)) {
    if (!value.length) return jsx('span', { style: MUTED, children: t('empty') })
    return jsx('div', {
      className: 'space-y-2',
      children: value.slice(0, 50).map((item, index) => jsxs('div', {
        className: 'grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border p-2.5',
        style: BORDER,
        children: [
          jsx('span', { className: 'font-mono text-xs', style: MUTED, children: `#${index + 1}` }),
          jsx(StructuredValue, { value: item, t, depth: depth + 1 })
        ]
      }, index))
    })
  }
  const entries = Object.entries(value).filter(([, item]) => item !== undefined && item !== null && item !== '')
  if (!entries.length) return jsx('span', { style: MUTED, children: t('empty') })
  return jsx('dl', {
    className: 'grid grid-cols-1 gap-2 sm:grid-cols-2',
    children: entries.slice(0, 50).map(([key, item]) => jsxs('div', {
      className: 'min-w-0 rounded-md border p-2.5',
      style: BORDER,
      children: [
        jsx('dt', { className: 'mb-1 text-xs font-medium', style: MUTED, children: humanize(key) }),
        jsx('dd', { children: jsx(StructuredValue, { value: item, t, depth: depth + 1 }) })
      ]
    }, key))
  })
}

function ErrorNotice({ error, title, t }) {
  if (!error) return null
  return jsx(ErrorState, {
    title: title || t('operationFailed'),
    description: messageFor(error)
  })
}

function LoadingLine({ label }) {
  return jsxs('div', {
    className: 'flex items-center gap-2 py-2 text-sm',
    style: MUTED,
    children: [jsx(GlyphSpinner, {}), label]
  })
}

function PageSkeleton() {
  return jsxs('div', {
    className: 'space-y-4',
    children: [
      jsx('div', {
        className: 'grid gap-3',
        style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 10rem), 1fr))' },
        children: [0, 1, 2, 3].map(index => jsx(Skeleton, { className: 'h-24 rounded-md' }, index))
      }),
      jsx('div', {
        className: 'grid gap-3',
        style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 24rem), 1fr))' },
        children: [0, 1].map(index => jsx(Skeleton, {
          className: 'rounded-md',
          style: { height: '14rem' }
        }, index))
      })
    ]
  })
}

function Hero({ snapshot, providers, t }) {
  const builtinEntries = finite(snapshot?.builtin?.total_entries,
    list(snapshot?.builtin?.stores).reduce((sum, store) => sum + finite(store?.entry_count, list(store?.entries).length), 0))
  return jsxs('section', {
    className: 'space-y-4',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-start justify-between gap-3',
        children: [
          jsxs('div', {
            children: [
              jsxs('div', {
                className: 'flex flex-wrap items-center gap-2',
                children: [
                  jsx('h2', { className: 'text-xl font-semibold tracking-tight', children: t('title') }),
                  jsx(Badge, { variant: 'outline', children: t('readOnly') })
                ]
              }),
              jsx('p', { className: 'mt-1 max-w-2xl text-sm', style: MUTED, children: t('subtitle') })
            ]
          }),
          providers.length ? jsx('div', {
            className: 'flex flex-wrap gap-1.5',
            children: providers.map(provider => jsx(Badge, {
              variant: 'muted',
              children: providerName(provider)
            }, provider))
          }) : null
        ]
      }),
      jsx(MetricGrid, {
        children: [
          jsx(StatCard, { label: t('totalEntries'), value: builtinEntries, hint: 'MEMORY.md + USER.md' }, 'entries'),
          jsx(StatCard, { label: t('activeProviders'), value: providers.length, hint: providers.map(providerName).join(' · ') || t('noProviders') }, 'providers'),
          jsx(StatCard, {
            label: t('holographicFacts'),
            value: finite(snapshot?.holographic?.total_facts),
            hint: `${finite(snapshot?.holographic?.fact_count)} ${t('shown').toLocaleLowerCase()}`
          }, 'facts'),
          jsx(StatCard, {
            label: t('lastSnapshot'),
            value: formatTime(snapshot?.generated_at, t),
            hint: snapshot?.version ? `v${snapshot.version}` : t('readOnly')
          }, 'snapshot')
        ]
      })
    ]
  })
}

function StoreCard({ store, fallbackName, t }) {
  const entries = list(store?.entries)
  const count = finite(store?.entry_count, entries.length)
  const used = store?.char_count
  const maximum = store?.char_limit
  const usage = store?.usage_percent
  return jsx(Card, {
    className: 'min-w-0',
    children: jsxs(Fragment, {
      children: [
        jsx(CardHeader, {
          className: 'pb-3',
          children: jsxs('div', {
            className: 'flex flex-wrap items-start justify-between gap-2',
            children: [
              jsxs('div', {
                className: 'min-w-0',
                children: [
                  jsx(CardTitle, {
                    className: 'text-base',
                    children: store?.label || store?.name || store?.filename || fallbackName
                  }),
                  store?.filename ? jsx('p', { className: 'mt-1 font-mono text-xs', style: MUTED, children: store.filename }) : null
                ]
              }),
              jsxs('div', {
                className: 'flex flex-wrap gap-1.5',
                children: [
                  jsx(Badge, { variant: 'outline', children: t('entryCount', count) }),
                  jsx(Badge, {
                    variant: store?.exists === false ? 'muted' : 'outline',
                    children: store?.exists === false ? t('unavailable') : t('available')
                  })
                ]
              })
            ]
          })
        }),
        jsx(CardContent, {
          className: 'space-y-4',
          children: jsxs(Fragment, {
            children: [
              jsx(ErrorNotice, { error: store?.error, t }),
              jsx(KeyValueGrid, {
                t,
                rows: [
                  { label: t('characterUsage'), value: used !== undefined && maximum !== undefined ? t('charsUsed', used, maximum) : undefined },
                  { label: t('status'), value: usage !== undefined && usage !== null ? t('percentUsed', usage) : undefined },
                  { label: t('modified'), value: store?.modified_at ? formatTime(store.modified_at, t) : undefined }
                ]
              }),
              jsx(UsageMeter, { value: usage, label: t('characterUsage') }),
              jsx(PathRow, { label: t('filePath'), value: store?.path }),
              entries.length
                ? jsx('div', {
                  className: 'space-y-2',
                  children: entries.map((entry, index) => {
                    const content = typeof entry === 'string' ? entry : entry?.content ?? entry?.text ?? entry?.value
                    return jsxs('div', {
                      className: 'grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border p-3',
                      style: BORDER,
                      children: [
                        jsx('span', { className: 'font-mono text-xs', style: MUTED, children: `#${index + 1}` }),
                        content !== undefined
                          ? jsx('div', {
                            className: 'whitespace-pre-wrap break-words text-sm leading-relaxed',
                            children: jsx(InlineText, { value: content })
                          })
                          : jsx(StructuredValue, { value: entry, t })
                      ]
                    }, entry?.id || `${store?.id || 'store'}-${index}`)
                  })
                })
                : jsx(EmptyState, { title: t('noEntries') })
            ]
          })
        })
      ]
    })
  })
}

function BuiltinStores({ builtin, t }) {
  const stores = Array.isArray(builtin?.stores)
    ? builtin.stores
    : Object.entries(builtin || {})
      .filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value))
      .map(([name, value]) => ({ name, ...value }))
  return jsxs('section', {
    className: 'space-y-3',
    children: [
      jsx(SectionHeading, {
        title: t('builtin'),
        description: t('builtinHint'),
        aside: jsx(Badge, { variant: 'outline', children: t('entryCount', finite(builtin?.total_entries, stores.reduce((sum, store) => sum + finite(store?.entry_count), 0))) })
      }),
      stores.length
        ? jsx('div', {
          className: 'grid gap-3',
          style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 24rem), 1fr))' },
          children: stores.map((store, index) => jsx(StoreCard, {
            store,
            fallbackName: t('storeNumber', index + 1),
            t
          }, store?.id || store?.name || index))
        })
        : jsx(EmptyState, { title: t('empty') })
    ]
  })
}

function FactCard({ fact, index, t }) {
  const factId = fact?.fact_id ?? fact?.id ?? index + 1
  const trust = score(fact?.trust_score ?? fact?.trust)
  return jsx(Card, {
    children: jsx(CardContent, {
      className: 'p-4',
      children: jsxs(Fragment, {
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-center gap-1.5',
            children: [
              jsx('span', { className: 'mr-1 font-mono text-xs', style: MUTED, children: t('factNumber', factId) }),
              fact?.category ? jsx(Badge, { variant: 'outline', children: fact.category }) : null,
              trust !== null ? jsx(Badge, { variant: 'muted', children: `${t('trust')} ${trust}` }) : null,
              jsx(Badge, { variant: 'outline', children: `${t('retrieved')} ${finite(fact?.retrieval_count)}×` }),
              jsx(Badge, { variant: 'outline', children: `${t('helpful')} ${finite(fact?.helpful_count)}×` })
            ]
          }),
          jsx('p', {
            className: 'mt-3 whitespace-pre-wrap break-words text-sm leading-relaxed',
            children: jsx(InlineText, { value: display(fact?.content ?? fact?.text ?? fact?.memory, t) })
          }),
          jsx(TagList, { value: fact?.tags, label: t('tags'), t }),
          jsxs('div', {
            className: 'mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs',
            style: MUTED,
            children: [
              fact?.updated_at ? jsx('span', { children: `${t('updated')}: ${formatTime(fact.updated_at, t)}` }) : null,
              fact?.created_at ? jsx('span', { children: `${t('created')}: ${formatTime(fact.created_at, t)}` }) : null
            ]
          })
        ]
      })
    })
  })
}

function FilterCard({ filters, updateFilter, refresh, snapshot, loading, t }) {
  const categories = list(snapshot?.holographic?.categories)
  const categoryOptions = [
    { value: '__all__', label: t('allCategories') },
    ...categories.map(item => ({
      value: item?.category || 'general',
      label: `${item?.category || 'general'} (${finite(item?.count)})`
    }))
  ]
  return jsx(Card, {
    children: jsxs(Fragment, {
      children: [
        jsx(CardHeader, {
          className: 'pb-2',
          children: jsxs(Fragment, {
            children: [
              jsx(CardTitle, { className: 'text-base', children: t('filters') }),
              jsx('p', { className: 'text-xs', style: MUTED, children: t('filterHint') })
            ]
          })
        }),
        jsx(CardContent, {
          className: 'flex flex-wrap items-end gap-3',
          children: jsxs(Fragment, {
            children: [
              jsx(Field, {
                label: t('search'),
                children: jsx(Input, {
                  value: filters.search,
                  onChange: event => updateFilter('search', event.target.value),
                  placeholder: t('searchPlaceholder')
                })
              }),
              jsx(Field, {
                label: t('category'),
                children: jsx(NativeSelect, {
                  value: filters.category || '__all__',
                  onValueChange: value => updateFilter('category', value === '__all__' ? '' : value),
                  placeholder: t('allCategories'),
                  options: categoryOptions
                })
              }),
              jsx(Field, {
                label: t('minTrust'),
                children: jsx(NativeSelect, {
                  value: filters.minTrust,
                  onValueChange: value => updateFilter('minTrust', Number(value)),
                  placeholder: '0.0',
                  options: ['0', '0.3', '0.5', '0.75'].map(value => ({ value, label: value }))
                })
              }),
              jsx(Field, {
                label: t('limit'),
                children: jsx(NativeSelect, {
                  value: filters.limit,
                  onValueChange: value => updateFilter('limit', Number(value)),
                  placeholder: String(QUERY_CONTROL_CONFIG.snapshot.defaultLimit),
                  options: QUERY_CONTROL_CONFIG.snapshot.limitOptions.map(value => ({
                    value,
                    label: String(value)
                  }))
                })
              }),
              jsx(Button, { onClick: refresh, disabled: loading, children: t('refresh') })
            ]
          })
        })
      ]
    })
  })
}

function HolographicProvider({ data, t }) {
  const facts = list(data?.facts)
  return jsxs('section', {
    className: 'space-y-3',
    children: [
      jsx(SectionHeading, {
        title: data?.label || 'Holographic',
        description: data?.db_path,
        aside: jsxs('div', {
          className: 'flex flex-wrap gap-1.5',
          children: [
            jsx(Badge, { variant: 'outline', children: t('configured') }),
            jsx(Badge, {
              variant: data?.exists === false ? 'muted' : 'outline',
              children: data?.exists === false ? t('unavailable') : t('available')
            })
          ]
        })
      }),
      jsx(MetricGrid, {
        children: [
          jsx(StatCard, { label: t('facts'), value: finite(data?.total_facts), hint: t('overview') }, 'facts'),
          jsx(StatCard, { label: t('shown'), value: finite(data?.fact_count, facts.length), hint: t('filters') }, 'shown'),
          jsx(StatCard, { label: t('entities'), value: finite(data?.entities_count), hint: t('overview') }, 'entities'),
          jsx(StatCard, { label: t('banks'), value: finite(data?.memory_banks_count), hint: t('overview') }, 'banks')
        ]
      }),
      jsx(ErrorNotice, { error: data?.error, t }),
      facts.length
        ? jsx('div', {
          className: 'space-y-2',
          children: facts.map((fact, index) => jsx(FactCard, { fact, index, t }, fact?.fact_id ?? fact?.id ?? index))
        })
        : jsx(EmptyState, { title: data?.exists === false ? t('noDatabase') : t('noFacts') })
    ]
  })
}

function itemContent(item) {
  if (typeof item === 'string') return item
  return item?.memory ?? item?.text ?? item?.content ?? item?.excerpt ?? item?.summary ?? item?.value ?? ''
}

function MemoryItemCard({ item, index, t, kind }) {
  const content = itemContent(item)
  const id = item?.id ?? item?.fact_id ?? index + 1
  const itemScore = score(item?.score ?? item?.similarity ?? item?.importance ?? item?.confidence)
  const type = item?.display_type ?? item?.type ?? item?.source
  const metadata = item?.metadata && typeof item.metadata === 'object' ? item.metadata : null
  const timestamp = item?.updated_at ?? item?.timestamp ?? item?.created_at
  return jsx(Card, {
    children: jsx(CardContent, {
      className: 'p-4',
      children: jsxs(Fragment, {
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-center gap-1.5',
            children: [
              jsx('span', { className: 'mr-1 font-mono text-xs', style: MUTED, children: `${kind || t('result')} #${id}` }),
              type ? jsx(Badge, { variant: 'outline', children: String(type) }) : null,
              itemScore !== null ? jsx(Badge, { variant: 'muted', children: `score ${itemScore}` }) : null,
              item?.user_id ? jsx(Badge, { variant: 'outline', children: `user ${item.user_id}` }) : null,
              item?.agent_id ? jsx(Badge, { variant: 'outline', children: `agent ${item.agent_id}` }) : null,
              item?.session_id ? jsx(Badge, { variant: 'outline', children: `session ${item.session_id}` }) : null
            ]
          }),
          item?.title ? jsx('p', { className: 'mt-3 text-sm font-medium', children: item.title }) : null,
          content
            ? jsx('p', { className: 'mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed', children: String(content) })
            : null,
          item?.path ? jsx(PathRow, { label: t('source'), value: item.path }) : null,
          item?.tags ? jsx(TagList, { value: item.tags, label: t('tags'), t }) : null,
          timestamp ? jsx('p', { className: 'mt-3 text-xs', style: MUTED, children: formatTime(timestamp, t) }) : null,
          metadata && Object.keys(metadata).length
            ? jsx('details', {
              className: 'mt-3',
              children: jsxs(Fragment, {
                children: [
                  jsx('summary', { className: 'cursor-pointer text-xs font-medium', style: MUTED, children: t('metadata') }),
                  jsx('div', { className: 'mt-2', children: jsx(StructuredValue, { value: metadata, t }) })
                ]
              })
            })
            : null
        ]
      })
    })
  })
}

function Collection({ items, title, empty, t, kind }) {
  const values = list(items)
  return jsxs('div', {
    className: 'space-y-2',
    children: [
      title ? jsxs('div', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx('h5', { className: 'text-sm font-semibold', children: title }),
          jsx(Badge, { variant: 'outline', children: t('itemCount', values.length) })
        ]
      }) : null,
      values.length
        ? values.map((item, index) => jsx(MemoryItemCard, { item, index, t, kind }, item?.id ?? `${kind || 'item'}-${index}`))
        : jsx(EmptyState, { title: empty || t('noMatches') })
    ]
  })
}

function ProviderShell({ data, name, stats, statusRows, path, children, actions, t }) {
  return jsx(Card, {
    children: jsxs(Fragment, {
      children: [
        jsx(CardHeader, {
          className: 'pb-3',
          children: jsx(SectionHeading, {
            title: data?.label || name,
            description: data?.mode || data?.mode_label || t('readOnly'),
            aside: jsxs('div', {
              className: 'flex flex-wrap gap-1.5',
              children: [
                jsx(Badge, { variant: 'outline', children: t('configured') }),
                data?.error ? jsx(Badge, { variant: 'muted', children: t('unavailable') }) : null
              ]
            })
          })
        }),
        jsx(CardContent, {
          className: 'space-y-4',
          children: jsxs(Fragment, {
            children: [
              stats?.length ? jsx(MetricGrid, {
                children: stats.map((stat, index) => jsx(StatCard, stat, stat.label || index))
              }) : null,
              statusRows?.length ? jsx(KeyValueGrid, { rows: statusRows, t }) : null,
              jsx(PathRow, { label: t('filePath'), value: path }),
              jsx(ErrorNotice, { error: data?.error, t }),
              children,
              actions
            ]
          })
        })
      ]
    })
  })
}

function Mem0Provider({ data, t }) {
  const memories = list(data?.memories)
  return jsx(ProviderShell, {
    data,
    name: 'Mem0',
    t,
    path: data?.config_path,
    stats: [
      { label: t('memories'), value: finite(data?.total_memories), hint: t('overview') },
      { label: t('shown'), value: finite(data?.memory_count, memories.length), hint: t('filters') },
      { label: 'User ID', value: display(data?.user_id, t), hint: t('source') },
      { label: 'Agent ID', value: display(data?.agent_id, t), hint: t('details') }
    ],
    statusRows: [
      { label: 'API key', value: data?.api_key_present },
      { label: t('status'), value: data?.config_exists },
      ...(data?.host ? [{ label: 'Host', value: data.host }] : [])
    ],
    children: jsx(Collection, { items: memories, title: t('memories'), t, kind: t('result') })
  })
}

function HonchoPeer({ title, peer, t }) {
  const card = list(peer?.card)
  const conclusions = list(peer?.conclusions)
  return jsx(Card, {
    children: jsxs(Fragment, {
      children: [
        jsx(CardHeader, {
          className: 'pb-3',
          children: jsxs('div', {
            className: 'flex flex-wrap items-start justify-between gap-2',
            children: [
              jsxs('div', {
                children: [
                  jsx(CardTitle, { className: 'text-sm', children: title }),
                  jsx('p', { className: 'mt-1 text-xs', style: MUTED, children: display(peer?.peer_id, t) })
                ]
              }),
              jsxs('div', {
                className: 'flex flex-wrap gap-1.5',
                children: [
                  jsx(Badge, { variant: 'outline', children: `${finite(peer?.total_card_facts, card.length)} ${t('cardFacts').toLocaleLowerCase()}` }),
                  jsx(Badge, { variant: 'outline', children: `${finite(peer?.total_conclusions, conclusions.length)} ${t('conclusions').toLocaleLowerCase()}` })
                ]
              })
            ]
          })
        }),
        jsx(CardContent, {
          className: 'space-y-4',
          children: jsxs(Fragment, {
            children: [
              card.length ? jsx('div', {
                className: 'space-y-2',
                children: card.map((item, index) => jsxs('div', {
                  className: 'grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border p-3 text-sm',
                  style: BORDER,
                  children: [
                    jsx('span', { className: 'font-mono text-xs', style: MUTED, children: `#${index + 1}` }),
                    jsx('span', { className: 'whitespace-pre-wrap break-words', children: String(item) })
                  ]
                }, index))
              }) : null,
              peer?.representation ? jsxs('div', {
                children: [
                  jsx('h5', { className: 'mb-2 text-xs font-medium', style: MUTED, children: t('representation') }),
                  jsx('p', { className: 'whitespace-pre-wrap break-words text-sm leading-relaxed', children: peer.representation })
                ]
              }) : null,
              conclusions.length ? jsx(Collection, {
                items: conclusions,
                title: t('conclusions'),
                t,
                kind: t('result')
              }) : null,
              !card.length && !peer?.representation && !conclusions.length ? jsx(EmptyState, { title: t('empty') }) : null
            ]
          })
        })
      ]
    })
  })
}

function HonchoProvider({ data, t }) {
  return jsx(ProviderShell, {
    data,
    name: 'Honcho',
    t,
    path: data?.config_path,
    stats: [
      { label: t('cardFacts'), value: finite(data?.user?.total_card_facts) + finite(data?.ai?.total_card_facts), hint: t('overview') },
      { label: t('conclusions'), value: finite(data?.user?.total_conclusions) + finite(data?.ai?.total_conclusions), hint: t('overview') },
      { label: t('shown'), value: finite(data?.search_result_count), hint: t('results') },
      { label: 'Workspace', value: display(data?.workspace, t), hint: display(data?.environment, t) }
    ],
    statusRows: [
      { label: 'Host', value: data?.host },
      { label: 'Recall mode', value: data?.recall_mode },
      { label: 'Session strategy', value: data?.session_strategy },
      { label: 'API / base URL', value: Boolean(data?.api_key_present || data?.base_url_present) }
    ],
    children: jsxs('div', {
      className: 'space-y-4',
      children: [
        list(data?.search_results).length ? jsx(Collection, {
          items: data.search_results,
          title: t('results'),
          t,
          kind: t('result')
        }) : null,
        jsx('div', {
          className: 'grid gap-3',
          style: { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 22rem), 1fr))' },
          children: [
            jsx(HonchoPeer, { title: t('userPeer'), peer: data?.user, t }, 'user'),
            jsx(HonchoPeer, { title: t('aiPeer'), peer: data?.ai, t }, 'ai')
          ]
        })
      ]
    })
  })
}

function MnemosyneSnapshot({ data, t }) {
  return jsxs('div', {
    className: 'space-y-4',
    children: [
      jsx(Collection, { items: data?.memories, title: t('memories'), t, kind: t('result') }),
      jsx(Collection, { items: data?.facts, title: t('facts'), t, kind: t('result') })
    ]
  })
}

function OperationResult({ mutation, provider, kind, t }) {
  if (!mutation) return null
  if (mutation.isPending) return jsx(LoadingLine, { label: t('loading') })
  if (mutation.error) return jsx(ErrorNotice, { error: mutation.error, t })
  const data = mutation.data
  if (data === undefined || data === null) return null
  if (data?.error) return jsx(ErrorNotice, { error: data.error, t })

  let content = null
  if (provider === 'hindsight' && kind === 'contents') {
    content = jsxs('div', {
      className: 'space-y-4',
      children: [
        jsx(Collection, { items: data?.memories, title: t('memories'), t, kind: t('result') }),
        jsx(Collection, { items: data?.documents, title: t('contents'), t, kind: t('result') })
      ]
    })
  } else if (provider === 'hindsight' && kind === 'recall') {
    content = jsx(Collection, { items: data?.results, title: t('results'), t, kind: t('result') })
  } else if (provider === 'hindsight' && kind === 'reflect') {
    content = data?.reflection
      ? jsx('p', { className: 'whitespace-pre-wrap break-words text-sm leading-relaxed', children: data.reflection })
      : jsx(EmptyState, { title: t('operationEmpty') })
  } else if (provider === 'mnemosyne' && kind === 'contents') {
    content = jsx(MnemosyneSnapshot, { data, t })
  } else if (provider === 'mnemosyne' && kind === 'recall') {
    content = jsx(Collection, { items: data?.results, title: t('results'), t, kind: t('result') })
  } else if (provider === 'mnemosyne' && kind === 'prefetch') {
    const context = data?.context ?? data?.result
    content = context
      ? jsx('p', { className: 'whitespace-pre-wrap break-words text-sm leading-relaxed', children: String(context) })
      : jsx(EmptyState, { title: t('operationEmpty') })
  } else if (provider === 'byterover') {
    const answer = data?.answer_summary || data?.answer
    content = jsxs('div', {
      className: 'space-y-3',
      children: [
        answer
          ? jsx('p', { className: 'whitespace-pre-wrap break-words text-sm leading-relaxed', children: answer })
          : jsx(EmptyState, { title: t('operationEmpty') }),
        list(data?.matched_docs).length ? jsx(StructuredValue, { value: data.matched_docs, t }) : null,
        data?.answer && data?.answer_summary && data.answer !== data.answer_summary
          ? jsx('details', {
            children: jsxs(Fragment, {
              children: [
                jsx('summary', { className: 'cursor-pointer text-xs font-medium', style: MUTED, children: t('details') }),
                jsx('p', { className: 'mt-2 whitespace-pre-wrap break-words text-sm', children: data.answer })
              ]
            })
          })
          : null
      ]
    })
  } else {
    content = jsx(StructuredValue, { value: data, t })
  }

  return jsx(Card, {
    children: jsxs(Fragment, {
      children: [
        jsx(CardHeader, {
          className: 'pb-2',
          children: jsx(CardTitle, { className: 'text-sm', children: t(kind === 'reflect' ? 'reflection' : kind === 'contents' ? 'contents' : 'result') })
        }),
        jsx(CardContent, { children: content })
      ]
    })
  })
}

function OperationControls({ provider, api, contents, t }) {
  const config = QUERY_CONTROL_CONFIG[provider]
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(config.defaultLimit)
  const [temporalWeight, setTemporalWeight] = useState(
    config.defaultTemporalWeight ?? QUERY_CONTROL_CONFIG.mnemosyne.defaultTemporalWeight
  )
  const recall = useMutation({
    mutationFn: controls => {
      const options = buildProviderOperationOptions(provider, 'recall', controls)
      return provider === 'hindsight'
        ? api.recallHindsight(options.query, options.limit)
        : api.recallMnemosyne(options.query, options.limit, options.temporalWeight)
    }
  })
  const secondary = useMutation({
    mutationFn: controls => {
      const kind = provider === 'hindsight' ? 'reflect' : 'prefetch'
      const options = buildProviderOperationOptions(provider, kind, controls)
      return provider === 'hindsight'
        ? api.reflectHindsight(options.query)
        : api.prefetchMnemosyne(options.query)
    }
  })
  const secondKind = provider === 'hindsight' ? 'reflect' : 'prefetch'
  const controls = { query, limit, temporalWeight }
  return jsxs('div', {
    className: 'space-y-3 rounded-md border p-3',
    style: BORDER,
    children: [
      jsx('p', { className: 'text-xs', style: MUTED, children: t('queryHint') }),
      jsxs('div', {
        className: 'flex flex-wrap items-end gap-2',
        children: [
          jsx(Field, {
            label: t('queryContentFilter'),
            children: jsx(Input, {
              value: query,
              onChange: event => setQuery(event.target.value),
              placeholder: t('queryContentPlaceholder')
            })
          }),
          jsx(Field, {
            label: t('limit'),
            children: jsx(NativeSelect, {
              value: limit,
              onValueChange: value => setLimit(Number(value)),
              placeholder: String(config.defaultLimit),
              options: config.limitOptions.map(value => ({ value, label: String(value) }))
            })
          })
        ].concat(provider === 'mnemosyne'
          ? jsx(Field, {
            label: t('temporalWeight'),
            children: jsx(NativeSelect, {
              value: temporalWeight,
              onValueChange: value => setTemporalWeight(Number(value)),
              placeholder: String(config.defaultTemporalWeight),
              options: config.temporalWeightOptions.map(value => ({
                value,
                label: String(value)
              }))
            })
          })
          : [])
      }),
      jsxs('div', {
        className: 'flex flex-wrap gap-2',
        children: [
          jsx(Button, {
            onClick: () => recall.mutate(controls),
            disabled: !query.trim() || recall.isPending,
            children: t('recall')
          }),
          jsx(Button, {
            onClick: () => secondary.mutate(controls),
            disabled: !query.trim() || secondary.isPending,
            children: t(secondKind)
          }),
          jsx(Button, {
            onClick: () => contents.mutate(
              buildProviderOperationOptions(provider, 'contents', controls)
            ),
            disabled: contents.isPending,
            children: t('loadContents')
          })
        ]
      }),
      jsx(OperationResult, { mutation: contents, provider, kind: 'contents', t }),
      jsx(OperationResult, { mutation: recall, provider, kind: 'recall', t }),
      jsx(OperationResult, { mutation: secondary, provider, kind: secondKind, t })
    ]
  })
}

function HindsightOperationControls({ api, t }) {
  const contents = useMutation({
    mutationFn: options => api.getHindsightContents(options)
  })
  useEffect(() => {
    contents.mutate(buildProviderOperationOptions('hindsight', 'contents', {
      query: '',
      limit: QUERY_CONTROL_CONFIG.hindsight.defaultLimit
    }))
  }, [])
  return jsx(OperationControls, { provider: 'hindsight', api, contents, t })
}

function MnemosyneOperationControls({ api, t }) {
  const contents = useMutation({
    mutationFn: options => api.getMnemosyneContents(options)
  })
  return jsx(OperationControls, { provider: 'mnemosyne', api, contents, t })
}

function MnemosyneProvider({ data, api, t }) {
  return jsx(ProviderShell, {
    data,
    name: 'Mnemosyne',
    t,
    path: data?.db_path,
    stats: [
      { label: t('memories'), value: finite(data?.total_memories), hint: `${finite(data?.memory_count)} ${t('shown').toLocaleLowerCase()}` },
      { label: t('facts'), value: finite(data?.total_facts), hint: `${finite(data?.fact_count)} ${t('shown').toLocaleLowerCase()}` },
      { label: 'Vectors', value: finite(data?.vector_rows), hint: t('overview') },
      { label: t('status'), value: data?.db_exists ? t('available') : t('unavailable'), hint: 'SQLite' }
    ],
    statusRows: [
      { label: 'Auto sleep', value: data?.auto_sleep_enabled },
      { label: 'Prefetch chars', value: data?.prefetch_content_chars },
      { label: 'Data directory', value: data?.data_dir }
    ],
    children: jsx(MnemosyneSnapshot, { data, t }),
    actions: jsx(MnemosyneOperationControls, { api, t })
  })
}

function HindsightProvider({ data, api, t }) {
  return jsx(ProviderShell, {
    data,
    name: 'Hindsight',
    t,
    path: data?.config_path,
    stats: [
      { label: t('banks'), value: display(data?.bank_id, t), hint: data?.bank_id_template || t('overview') },
      { label: 'Budget', value: display(data?.recall_budget, t), hint: t('recall') },
      { label: 'Memory mode', value: display(data?.memory_mode, t), hint: t('status') },
      { label: 'Auto', value: `${data?.auto_recall ? t('recall') : t('unknown')} / ${data?.auto_retain ? 'retain' : t('unknown')}`, hint: t('status') }
    ],
    statusRows: [
      { label: 'Provider mode', value: data?.mode },
      { label: 'LLM provider', value: data?.llm_provider },
      { label: 'LLM model', value: data?.llm_model },
      { label: 'API key', value: data?.api_key_present },
      { label: 'LLM key', value: data?.llm_key_present }
    ],
    actions: jsx(HindsightOperationControls, { api, t })
  })
}

function ByteRoverActions({ api, t }) {
  const [query, setQuery] = useState('')
  const operation = useMutation({
    mutationFn: value => api.queryByteRover(
      value,
      QUERY_CONTROL_CONFIG.byterover.queryTimeout
    )
  })
  return jsxs('div', {
    className: 'space-y-3 rounded-md border p-3',
    style: BORDER,
    children: [
      jsx(Field, {
        label: t('query'),
        children: jsx(Textarea, {
          value: query,
          onChange: event => setQuery(event.target.value),
          placeholder: t('queryHint')
        })
      }),
      jsx(Button, {
        onClick: () => operation.mutate(query),
        disabled: !query.trim() || operation.isPending,
        children: t('byteRover')
      }),
      jsx(OperationResult, { mutation: operation, provider: 'byterover', kind: 'result', t })
    ]
  })
}

function ByteRoverProvider({ data, api, t }) {
  const status = data?.status && typeof data.status === 'object' ? data.status : {}
  return jsx(ProviderShell, {
    data,
    name: 'ByteRover',
    t,
    path: data?.project_root || data?.config_path,
    stats: [
      { label: t('results'), value: finite(data?.total_found, data?.result_count), hint: `${finite(data?.result_count)} ${t('shown').toLocaleLowerCase()}` },
      { label: 'Locations', value: finite(data?.location_count, list(data?.locations).length), hint: t('source') },
      { label: 'CLI', value: data?.brv_available ? t('available') : t('unavailable'), hint: data?.brv_path },
      { label: 'Project', value: data?.project_exists ? t('available') : t('unavailable'), hint: data?.search_scope || t('overview') }
    ],
    statusRows: Object.entries(status).slice(0, 9).map(([label, value]) => ({
      label: humanize(label),
      value: typeof value === 'object' ? undefined : value
    })),
    children: jsxs('div', {
      className: 'space-y-4',
      children: [
        list(data?.results).length ? jsx(Collection, { items: data.results, title: t('results'), t, kind: t('result') }) : null,
        list(data?.locations).length ? jsxs('details', {
          children: [
            jsx('summary', { className: 'cursor-pointer text-xs font-medium', style: MUTED, children: `Locations (${data.locations.length})` }),
            jsx('div', { className: 'mt-2', children: jsx(StructuredValue, { value: data.locations, t }) })
          ]
        }) : null
      ]
    }),
    actions: jsx(ByteRoverActions, { api, t })
  })
}

function GenericProvider({ provider, data, t }) {
  const ignored = new Set(['id', 'label', 'provider_configured', 'mode', 'error', 'generated_at'])
  const rows = Object.entries(data || {})
    .filter(([key, value]) => !ignored.has(key) && !Array.isArray(value) && (typeof value !== 'object' || value === null))
    .slice(0, 12)
    .map(([key, value]) => ({ label: humanize(key), value }))
  const collections = Object.entries(data || {}).filter(([, value]) => Array.isArray(value) && value.length)
  return jsx(ProviderShell, {
    data,
    name: providerName(provider),
    t,
    path: data?.config_path || data?.db_path,
    statusRows: rows,
    children: collections.length
      ? jsx('div', {
        className: 'space-y-4',
        children: collections.map(([key, values]) => jsx(Collection, {
          items: values,
          title: humanize(key),
          t,
          kind: t('result')
        }, key))
      })
      : null
  })
}

function providerName(provider) {
  if (provider === 'byterover') return 'ByteRover'
  return `${provider?.charAt(0).toUpperCase()}${provider?.slice(1)}`
}

function ProviderView({ provider, snapshot, api, t }) {
  const data = snapshot?.[provider]
  if (provider === 'holographic') return jsx(HolographicProvider, { data, t })
  if (provider === 'mem0') return jsx(Mem0Provider, { data, t })
  if (provider === 'honcho') return jsx(HonchoProvider, { data, t })
  if (provider === 'mnemosyne') return jsx(MnemosyneProvider, { data, api, t })
  if (provider === 'hindsight') return jsx(HindsightProvider, { data, api, t })
  if (provider === 'byterover') return jsx(ByteRoverProvider, { data, api, t })
  return jsx(GenericProvider, { provider, data, t })
}

function SessionResult({ result, index, t }) {
  const messages = list(result?.messages).slice(0, 4)
  const title = result?.title || result?.session_id || t('session')
  return jsx(Card, {
    children: jsx(CardContent, {
      className: 'p-4',
      children: jsxs(Fragment, {
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-center gap-1.5',
            children: [
              jsx(Badge, { variant: 'outline', children: result?.source || t('session') }),
              result?.model ? jsx(Badge, { variant: 'muted', children: result.model }) : null,
              result?.when ? jsx('span', { className: 'text-xs', style: MUTED, children: result.when }) : null,
              result?.match_message_id ? jsx('span', { className: 'text-xs', style: MUTED, children: `#${result.match_message_id}` }) : null
            ]
          }),
          jsx('h5', { className: 'mt-3 break-words text-sm font-semibold', children: title }),
          result?.snippet ? jsx('p', {
            className: 'mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed',
            style: MUTED,
            children: result.snippet
          }) : null,
          messages.length ? jsxs('details', {
            className: 'mt-3',
            children: [
              jsx('summary', { className: 'cursor-pointer text-xs font-medium', style: MUTED, children: `${t('messages')} (${messages.length})` }),
              jsx('div', {
                className: 'mt-2 space-y-2',
                children: messages.map((message, messageIndex) => jsxs('div', {
                  className: 'grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border p-3',
                  style: BORDER,
                  children: [
                    jsx(Badge, { variant: message?.anchor ? 'muted' : 'outline', children: message?.role || 'msg' }),
                    jsx('p', { className: 'whitespace-pre-wrap break-words text-sm', children: display(message?.content, t) })
                  ]
                }, message?.id ?? messageIndex))
              })
            ]
          }) : null
        ]
      })
    })
  }, result?.session_id || index)
}

function SessionSearch({ api, t }) {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [sort, setSort] = useState(QUERY_CONTROL_CONFIG.session.defaultSort)
  const search = useMutation({ mutationFn: values => api.searchSessions(values) })
  const submit = event => {
    event.preventDefault()
    if (query.trim()) {
      search.mutate({
        query: query.trim(),
        source,
        sort,
        limit: QUERY_CONTROL_CONFIG.session.defaultLimit
      })
    }
  }
  const results = list(search.data?.results)
  const sourceOptions = [
    { value: '__all__', label: t('allSources') },
    ...['cli', 'telegram', 'discord', 'web', 'api-server', 'cron'].map(value => ({ value, label: value }))
  ]
  return jsxs('section', {
    className: 'space-y-3',
    children: [
      jsx(SectionHeading, {
        title: t('sessions'),
        description: t('sessionHint'),
        aside: search.data ? jsx(Badge, { variant: 'outline', children: t('itemCount', finite(search.data?.count, results.length)) }) : null
      }),
      jsx(Card, {
        children: jsx(CardContent, {
          className: 'p-4',
          children: jsxs('form', {
            className: 'flex flex-wrap items-end gap-3',
            onSubmit: submit,
            children: [
              jsx(Field, {
                label: t('search'),
                children: jsx(Input, {
                  value: query,
                  onChange: event => setQuery(event.target.value),
                  placeholder: t('searchPlaceholder')
                })
              }),
              jsx(Field, {
                label: t('source'),
                children: jsx(NativeSelect, {
                  value: source || '__all__',
                  onValueChange: value => setSource(value === '__all__' ? '' : value),
                  placeholder: t('allSources'),
                  options: sourceOptions
                })
              }),
              jsx(Field, {
                label: t('sortOrder'),
                children: jsx(NativeSelect, {
                  value: sort,
                  onValueChange: setSort,
                  placeholder: t('newest'),
                  options: QUERY_CONTROL_CONFIG.session.sortOptions.map(value => ({
                    value,
                    label: t(value)
                  }))
                })
              }),
              jsx(Button, {
                type: 'submit',
                disabled: !query.trim() || search.isPending,
                children: search.isPending ? t('searching') : t('runSearch')
              })
            ]
          })
        })
      }),
      search.isPending ? jsx(LoadingLine, { label: t('searching') }) : null,
      jsx(ErrorNotice, { error: search.error || search.data?.error, t }),
      !search.isPending && search.data && !search.data?.error
        ? results.length
          ? jsx('div', {
            className: 'space-y-2',
            children: results.map((result, index) => jsx(SessionResult, { result, index, t }, result?.session_id || index))
          })
          : jsx(EmptyState, { title: t('noSessions') })
        : !search.isPending && search.data === undefined
          ? jsx(EmptyState, { title: t('operationEmpty') })
          : null
    ]
  })
}

function MemoryPage({ ctx }) {
  const t = usePluginI18n(PLUGIN_ID)
  const api = useMemo(() => createMemoryApi(ctx), [ctx])
  const initialFilters = normalizeSnapshotFilters()
  const [filters, setFilters] = useState(initialFilters)
  const [appliedFilters, setAppliedFilters] = useState(initialFilters)
  const snapshot = useQuery({
    queryKey: [PLUGIN_ID, 'snapshot', appliedFilters.limit, appliedFilters.minTrust, appliedFilters.category, appliedFilters.search],
    queryFn: () => api.getSnapshot(appliedFilters),
    staleTime: 10_000
  })
  const updateFilter = (key, value) => setFilters(current => ({ ...current, [key]: value }))
  const providers = visibleProviderKeys(snapshot.data)
  const refresh = () => {
    const normalized = normalizeSnapshotFilters(filters)
    const changed = Object.keys(normalized).some(key => normalized[key] !== appliedFilters[key])
    if (changed) setAppliedFilters(normalized)
    else snapshot.refetch()
  }

  return jsx('div', {
    className: 'h-full min-w-0 w-full',
    style: {
      maxWidth: '100%',
      minWidth: 0,
      overflowX: 'hidden',
      overflowY: 'auto',
      width: 'calc(100vw - var(--workspace-left, 0px) - var(--workspace-right, 0px))'
    },
    children: jsx('main', {
      className: 'mx-auto flex w-full flex-col gap-6 p-4',
      style: { boxSizing: 'border-box', maxWidth: '80rem', minWidth: 0 },
      children: jsxs(Fragment, {
        children: [
          snapshot.data
            ? jsx(Hero, { snapshot: snapshot.data, providers, t })
            : jsxs('header', {
              children: [
                jsxs('div', {
                  className: 'flex items-center gap-2',
                  children: [
                    jsx('h2', { className: 'text-xl font-semibold', children: t('title') }),
                    jsx(Badge, { variant: 'outline', children: t('readOnly') })
                  ]
                }),
                jsx('p', { className: 'mt-1 text-sm', style: MUTED, children: t('subtitle') })
              ]
            }),
          jsx(FilterCard, {
            filters,
            updateFilter,
            refresh,
            snapshot: snapshot.data,
            loading: snapshot.isLoading,
            t
          }),
          snapshot.isLoading ? jsx(PageSkeleton, {}) : null,
          jsx(ErrorNotice, { error: snapshot.error, title: t('failed'), t }),
          snapshot.data ? jsx(BuiltinStores, { builtin: snapshot.data.builtin, t }) : null,
          snapshot.data ? jsx(Separator, {}) : null,
          snapshot.data ? jsxs('section', {
            className: 'space-y-4',
            children: [
              jsx(SectionHeading, {
                title: t('providers'),
                description: t('providerHint'),
                aside: jsx(Badge, { variant: 'outline', children: t('itemCount', providers.length) })
              }),
              providers.length
                ? jsx('div', {
                  className: 'space-y-4',
                  children: providers.map(provider => jsx(ProviderView, {
                    provider,
                    snapshot: snapshot.data,
                    api,
                    t
                  }, provider))
                })
                : jsx(EmptyState, { title: t('noProviders') })
            ]
          }) : null,
          jsx(Separator, {}),
          jsx(SessionSearch, { api, t })
        ]
      })
    })
  })
}

function register(ctx) {
  ctx.i18n.register(bundles)
  const navLabel = ctx.i18n.t('title')
  const openLabel = ctx.i18n.t('openMemory')
  ctx.register({
    id: 'page',
    area: ROUTES_AREA,
    data: { path: PLUGIN_ROUTE },
    render: () => jsx(MemoryPage, { ctx })
  })
  ctx.register({
    id: 'nav',
    area: SIDEBAR_NAV_AREA,
    data: { path: PLUGIN_ROUTE, label: navLabel, codicon: 'database' }
  })
  ctx.register({
    id: 'open',
    area: PALETTE_AREA,
    data: {
      id: `${PLUGIN_ID}.open`,
      label: openLabel,
      keywords: ['memory', 'memories', 'pamięć'],
      run: () => host.navigate(PLUGIN_ROUTE)
    }
  })
}

export default {
  id: PLUGIN_ID,
  name: PLUGIN_NAME,
  version: VERSION,
  register
}
