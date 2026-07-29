import fs from 'node:fs/promises'
import process from 'node:process'
import vm from 'node:vm'

const pluginPath = process.argv[2]
if (!pluginPath) throw new Error('desktop plugin path is required')

const source = await fs.readFile(pluginPath, 'utf8')
const navigations = []
const sdkValues = {
  Badge: function Badge() {},
  Button: function Button() {},
  Codicon: function Codicon() {},
  EmptyState: function EmptyState() {},
  ErrorState: function ErrorState() {},
  GlyphSpinner: function GlyphSpinner() {},
  Input: function Input() {},
  PALETTE_AREA: 'palette.commands',
  ROUTES_AREA: 'routes',
  ScrollArea: function ScrollArea() {},
  Select: function Select() {},
  SelectContent: function SelectContent() {},
  SelectItem: function SelectItem() {},
  SelectTrigger: function SelectTrigger() {},
  SelectValue: function SelectValue() {},
  Separator: function Separator() {},
  SIDEBAR_NAV_AREA: 'sidebar.nav',
  Skeleton: function Skeleton() {},
  Textarea: function Textarea() {},
  cn: (...values) => values.filter(Boolean).join(' '),
  fmtDateTime: value => String(value ?? ''),
  host: {
    navigate: path => navigations.push(path),
    notify: () => {},
    notifyError: () => {}
  },
  icons: {},
  useMutation: () => ({ mutate: () => {}, isPending: false, error: null }),
  usePluginI18n: () => (key => key),
  useQuery: () => ({ data: null, isLoading: false, error: null, refetch: () => {} }),
  useQueryClient: () => ({ invalidateQueries: () => {} })
}

const reactValues = {
  Fragment: Symbol.for('react.fragment'),
  useEffect: () => {},
  useMemo: fn => fn(),
  useState: initial => [initial, () => {}]
}

const runtimeValues = {
  Fragment: Symbol.for('react.fragment'),
  jsx: (type, props) => ({ type, props: props ?? {} }),
  jsxs: (type, props) => ({ type, props: props ?? {} })
}

const context = vm.createContext({
  URL,
  URLSearchParams,
  clearTimeout,
  console,
  Promise,
  setTimeout
})

function synthetic(identifier, values) {
  const names = Object.keys(values)
  return new vm.SyntheticModule(
    names,
    function initialize() {
      for (const name of names) this.setExport(name, values[name])
    },
    { context, identifier }
  )
}

const dependencies = {
  '@hermes/plugin-sdk': synthetic('@hermes/plugin-sdk', sdkValues),
  react: synthetic('react', reactValues),
  'react/jsx-runtime': synthetic('react/jsx-runtime', runtimeValues)
}

const module = new vm.SourceTextModule(source, { context, identifier: pluginPath })
await module.link(async specifier => {
  const dependency = dependencies[specifier]
  if (!dependency) throw new Error(`unsupported import: ${specifier}`)
  return dependency
})
await module.evaluate()

const plugin = module.namespace.default
if (!plugin || typeof plugin.register !== 'function') {
  throw new Error('desktop plugin must default-export a registerable plugin')
}

const contributions = []
const restPaths = []
const restTimeouts = []
let localeBundles = null
const translatedKeys = []
const ctx = {
  i18n: {
    register: bundles => {
      localeBundles = bundles
      return () => {}
    },
    t: key => {
      translatedKeys.push(key)
      return { title: 'Memory', openMemory: 'Open Memory' }[key] ?? key
    }
  },
  register: contribution => {
    contributions.push(contribution)
    return () => {}
  },
  registerMany: values => {
    contributions.push(...values)
    return () => {}
  },
  rest: async (path, options = {}) => {
    restPaths.push(path)
    restTimeouts.push(options.timeoutMs ?? null)
    return {}
  },
  storage: {
    get: (_key, fallback) => fallback,
    remove: () => {},
    set: () => {}
  }
}

plugin.register(ctx)

const route = contributions.find(item => item.area === sdkValues.ROUTES_AREA)
const sidebar = contributions.find(item => item.area === sdkValues.SIDEBAR_NAV_AREA)
const palette = contributions.find(item => item.area === sdkValues.PALETTE_AREA)
if (!route || !sidebar || !palette) throw new Error('missing desktop route, sidebar, or palette contribution')
if (typeof route.render !== 'function') throw new Error('desktop route must render a page')
palette.data.run()

const createMemoryApi = module.namespace.createMemoryApi
const buildProviderOperationOptions = module.namespace.buildProviderOperationOptions
const normalizeSnapshotFilters = module.namespace.normalizeSnapshotFilters
const queryControlConfig = module.namespace.QUERY_CONTROL_CONFIG
const visibleProviderKeys = module.namespace.visibleProviderKeys
if (
  typeof createMemoryApi !== 'function' ||
  typeof buildProviderOperationOptions !== 'function' ||
  typeof normalizeSnapshotFilters !== 'function' ||
  !queryControlConfig ||
  typeof visibleProviderKeys !== 'function'
) {
  throw new Error('desktop plugin must export testable API, query-control, filter, and visibility helpers')
}

const api = createMemoryApi(ctx)
await api.getSnapshot()
await api.getSnapshot({ limit: 25, minTrust: 0.3, category: 'project', search: 'hello world' })
await api.searchSessions({ query: 'memory search', limit: 3, sort: 'newest', source: 'telegram' })
await api.queryByteRover('what changed?', 60)
await api.getHindsightContents({ search: 'dashboard', limit: 50 })
await api.recallHindsight('remember dashboard', 50)
await api.reflectHindsight('summarize dashboard')
await api.getMnemosyneContents({ search: 'dashboard', limit: 100 })
await api.recallMnemosyne('remember dashboard', 100, 0.8)
await api.prefetchMnemosyne('inject dashboard')

const visibleProviders = visibleProviderKeys({
  holographic: { provider_configured: true },
  mem0: { provider_configured: false },
  honcho: { provider_configured: true },
  mnemosyne: { provider_configured: false },
  hindsight: { provider_configured: true },
  byterover: { provider_configured: false }
})
const normalizedFilters = normalizeSnapshotFilters({
  category: '  project  ',
  limit: 9999,
  minTrust: -2,
  search: '  hello world  '
})
const defaultFilters = normalizeSnapshotFilters()
const operationOptions = {
  hindsightContents: buildProviderOperationOptions('hindsight', 'contents', {
    query: '  release plan  ',
    limit: 50
  }),
  hindsightRecall: buildProviderOperationOptions('hindsight', 'recall', {
    query: '  release plan  ',
    limit: 50
  }),
  hindsightReflect: buildProviderOperationOptions('hindsight', 'reflect', {
    query: '  release plan  ',
    limit: 50
  }),
  mnemosyneContents: buildProviderOperationOptions('mnemosyne', 'contents', {
    query: '  release plan  ',
    limit: 100,
    temporalWeight: 0.8
  }),
  mnemosyneRecall: buildProviderOperationOptions('mnemosyne', 'recall', {
    query: '  release plan  ',
    limit: 100,
    temporalWeight: 0.8
  }),
  mnemosynePrefetch: buildProviderOperationOptions('mnemosyne', 'prefetch', {
    query: '  release plan  ',
    limit: 100,
    temporalWeight: 0.8
  })
}

process.stdout.write(JSON.stringify({
  defaultFilters,
  i18nLocales: Object.keys(localeBundles ?? {}).sort(),
  normalizedFilters,
  operationOptions,
  paletteDataId: palette.data.id,
  paletteNavigation: navigations.at(-1),
  plugin: { id: plugin.id, name: plugin.name },
  queryControlConfig,
  restPaths,
  restTimeouts,
  route: route.data.path,
  sidebar: { path: sidebar.data.path, label: sidebar.data.label },
  translatedKeys,
  visibleProviders
}))
