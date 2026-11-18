import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import process from 'node:process'
import vm from 'node:vm'

const pluginPath = process.argv[2]
if (!pluginPath) throw new Error('desktop plugin path is required')

const source = await fs.readFile(pluginPath, 'utf8')
const navigations = []
let queryHook = () => ({ data: null, isLoading: false, error: null, refetch: () => {} })
let stateHook = initial => [initial, () => {}]
let activeConnection = 'gateway-a'
let activeHostProfile = 'default'
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
    state: {
      connectionId: { get: () => activeConnection },
      profile: { get: () => activeHostProfile }
    },
    navigate: path => navigations.push(path),
    notify: () => {},
    notifyError: () => {}
  },
  icons: {},
  useMutation: () => ({ mutate: () => {}, isPending: false, error: null }),
  usePluginI18n: () => (key => key),
  useQuery: options => queryHook(options),
  useValue: atom => atom.get(),
  useQueryClient: () => ({ invalidateQueries: () => {} })
}

const reactValues = {
  Fragment: Symbol.for('react.fragment'),
  useEffect: () => {},
  useMemo: fn => fn(),
  useState: initial => stateHook(initial)
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

// Exercise the real section and handlers while controlling query completion.
const builtinPaths = []
const builtinApi = createMemoryApi({
  rest: async path => {
    builtinPaths.push(path)
    return { stores: [{ id: path, entries: [path] }] }
  }
})
await builtinApi.getBuiltinProfiles()
await builtinApi.getBuiltin('default')
await builtinApi.getBuiltin('work bot')
await builtinApi.getBuiltin()
assert.deepEqual(builtinPaths, [
  '/builtin/profiles',
  '/builtin?memory_profile=default',
  '/builtin?memory_profile=work+bot',
  '/builtin?memory_profile=current'
])

const BuiltinMemorySection = module.namespace.BuiltinMemorySection
assert.equal(typeof BuiltinMemorySection, 'function')
let selectedProfile = 'current'
let memoryData = null
let memoryError = null
let memoryQuery
let refreshedSnapshot = 0
let refreshedProfiles = 0
let refreshedMemory = 0
let availableProfiles = [
  { name: 'current', label: 'Active profile' },
  { name: 'default', label: 'default' },
  { name: 'alpha', label: 'Research bot (alpha)' },
  { name: 'beta', label: 'beta' }
]
const scoped = value => ({ connectionId: activeConnection, hostProfile: activeHostProfile, value })
stateHook = () => [selectedProfile, value => { selectedProfile = value }]
queryHook = options => {
  if (options.queryKey[1] === 'builtin-profiles') {
    return { data: scoped({ profiles: availableProfiles }), refetch: () => { refreshedProfiles++ } }
  }
  memoryQuery = options
  return {
    data: memoryData,
    error: memoryError,
    isLoading: !memoryData && !memoryError,
    refetch: () => { refreshedMemory++ }
  }
}
const sdkComponents = new Set(Object.values(sdkValues))
function expand(node) {
  if (node === null || node === undefined || typeof node !== 'object') return node
  if (Array.isArray(node)) return node.map(expand)
  if (typeof node.type === 'function' && !sdkComponents.has(node.type)) return expand(node.type(node.props))
  return { ...node, props: { ...node.props, children: expand(node.props?.children) } }
}
function find(node, predicate) {
  if (!node || typeof node !== 'object') return null
  if (Array.isArray(node)) return node.map(item => find(item, predicate)).find(Boolean)
  return predicate(node) ? node : find(node.props?.children, predicate)
}
function textContent(node) {
  if (node === null || node === undefined || node === false) return ''
  if (Array.isArray(node)) return node.map(textContent).join(' ')
  if (typeof node !== 'object') return String(node)
  return textContent(node.props?.children)
}
const currentBuiltin = { stores: [{ filename: 'MEMORY.md', entries: ['active memory'], path: '/active/memories/MEMORY.md' }] }
const renderBuiltin = () => expand(BuiltinMemorySection({
  api: builtinApi,
  builtin: currentBuiltin,
  refreshSnapshot: () => { refreshedSnapshot++ },
  t: key => key
}))
let builtinTree = renderBuiltin()
assert.equal(memoryQuery.enabled, false)
assert.match(textContent(builtinTree), /active memory/)
let selector = find(builtinTree, node => node.type === sdkValues.Select)
assert.ok(selector)
assert.match(textContent(selector), /Research bot \(alpha\)/)
find(builtinTree, node => node.type === sdkValues.Button).props.onClick()
assert.equal(refreshedSnapshot, 1)
assert.equal(refreshedProfiles, 1)

selector.props.onValueChange('alpha')
builtinTree = renderBuiltin()
assert.equal(memoryQuery.queryKey[2], 'alpha')
assert.equal(memoryQuery.enabled, true)
assert.doesNotMatch(textContent(builtinTree), /active memory/)
const alphaResponse = await memoryQuery.queryFn()
find(builtinTree, node => node.type === sdkValues.Select).props.onValueChange('beta')
memoryData = alphaResponse
builtinTree = renderBuiltin()
assert.equal(memoryQuery.queryKey[2], 'beta')
assert.doesNotMatch(textContent(builtinTree), /memory_profile=alpha/)
memoryData = await memoryQuery.queryFn()
builtinTree = renderBuiltin()
assert.match(textContent(builtinTree), /memory_profile=beta/)
assert.doesNotMatch(textContent(builtinTree), /active memory/)
find(builtinTree, node => node.type === sdkValues.Button).props.onClick()
assert.equal(refreshedMemory, 1)
assert.equal(refreshedSnapshot, 1)

memoryError = new Error('profile deleted')
availableProfiles = [{ name: 'current', label: 'Active profile' }]
builtinTree = renderBuiltin()
assert.doesNotMatch(textContent(builtinTree), /memory_profile=beta/)
assert.ok(find(builtinTree, node => node.type === sdkValues.ErrorState))
selector = find(builtinTree, node => node.type === sdkValues.Select)
assert.equal(selector.props.value, 'beta')
assert.match(textContent(selector), /beta \(unavailable\)/)
assert.ok(find(selector, node => node.type === sdkValues.SelectItem && node.props.value === 'current'))
assert.ok(find(selector, node => node.type === sdkValues.SelectItem && node.props.value === 'beta'))
find(builtinTree, node => node.type === sdkValues.Select).props.onValueChange('current')
builtinTree = renderBuiltin()
assert.match(textContent(builtinTree), /active memory/)
assert.equal(memoryQuery.enabled, false)

availableProfiles = [{ name: 'current', label: 'Active profile' }]
builtinTree = renderBuiltin()
selector = find(builtinTree, node => node.type === sdkValues.Select)
const profileItems = []
function collectItems(node) {
  if (!node || typeof node !== 'object') return
  if (Array.isArray(node)) return node.forEach(collectItems)
  if (node.type === sdkValues.SelectItem) profileItems.push(node.props.value)
  collectItems(node.props?.children)
}
collectItems(selector)
assert.deepEqual(profileItems, ['current'])
const builtinProfileChecks = {
  paths: builtinPaths,
  currentSnapshotReused: true,
  selectionScopesQueries: true,
  staleMemoryHidden: true,
  failedMemoryHidden: true,
  removedSelectionRetained: true,
  legacyCurrentOnly: true
}

// Retain the previous result across key changes, as a host query client can do,
// and control network completion independently of the currently selected route.
const scopeQueries = new Map()
const scopeResults = new Map()
let pendingReads = []
let scopedRestCalls = 0
const scopedRest = path => {
  scopedRestCalls++
  return new Promise(resolve => pendingReads.push({ path, resolve }))
}
const scopedApi = createMemoryApi({ rest: scopedRest })
ctx.rest = scopedRest
queryHook = options => {
  const kind = options.queryKey[1]
  scopeQueries.set(kind, options)
  return { data: scopeResults.get(kind), isLoading: !scopeResults.has(kind), refetch: () => {} }
}
stateHook = initial => typeof initial === 'string'
  ? [selectedProfile, value => { selectedProfile = value }]
  : [initial, () => {}]
const storesFor = entry => ({ stores: [{ filename: 'MEMORY.md', entries: [entry] }] })
const scopedSection = () => expand(BuiltinMemorySection({
  api: scopedApi, builtin: null, refreshSnapshot: () => {}, t: key => key
}))
const scopedPage = () => expand(route.render())
async function completeRead(kind, value) {
  const promise = scopeQueries.get(kind).queryFn()
  pendingReads.shift().resolve(value)
  scopeResults.set(kind, await promise)
}
for (const changeRoute of [
  () => { activeConnection = 'gateway-b' },
  () => { activeHostProfile = 'research' }
]) {
  activeConnection = 'gateway-a'
  activeHostProfile = 'default'
  selectedProfile = 'default'
  scopeResults.clear()
  scopedSection()
  await completeRead('builtin-profiles', { profiles: [{ name: 'default' }, { name: 'only-on-A' }] })
  await completeRead('builtin', storesFor('A-private-selected'))
  assert.match(textContent(scopedSection()), /A-private-selected/)
  assert.match(textContent(scopedSection()), /only-on-A/)
  scopedPage()
  await completeRead('snapshot', { builtin: storesFor('A-private-current') })
  selectedProfile = 'current'
  assert.match(textContent(scopedPage()), /A-private-current/)
  selectedProfile = 'default'
  scopedSection()
  const oldQueries = new Map(scopeQueries)
  const lateReads = [...oldQueries].map(([kind, options]) => ({ kind, promise: options.queryFn() }))
  const lateResolvers = pendingReads
  pendingReads = []
  changeRoute()
  // The same selected profile name must not accept data from the previous route.
  assert.doesNotMatch(textContent(scopedSection()), /A-private-selected|only-on-A/)
  selectedProfile = 'current'
  assert.doesNotMatch(textContent(scopedPage()), /A-private-current|A-private-selected/)
  selectedProfile = 'default'
  scopedSection()
  for (const [kind, oldQuery] of oldQueries) {
    assert.notDeepEqual(scopeQueries.get(kind).queryKey, oldQuery.queryKey)
    const callsBeforeRetry = scopedRestCalls
    await assert.rejects(oldQuery.queryFn(), /connection or active profile changed/)
    assert.equal(scopedRestCalls, callsBeforeRetry, 'an old retry must not request the new route')
  }
  lateResolvers.forEach(read => read.resolve(storesFor('A-late-private')))
  for (const read of lateReads) await assert.rejects(read.promise, /connection or active profile changed/)
  assert.doesNotMatch(textContent(scopedSection()), /A-private|A-late-private|only-on-A/)
  // Even while B's request is pending, the retained A cache is hidden.
  const pendingMemory = scopeQueries.get('builtin').queryFn()
  assert.doesNotMatch(textContent(scopedSection()), /A-private|A-late-private/)
  pendingReads.shift().resolve(storesFor('B-selected'))
  scopeResults.set('builtin', await pendingMemory)
  await completeRead('builtin-profiles', { profiles: [{ name: 'default' }, { name: 'only-on-B' }] })
  assert.match(textContent(scopedSection()), /B-selected/)
  assert.match(textContent(scopedSection()), /only-on-B/)
  scopedPage()
  await completeRead('snapshot', { builtin: storesFor('B-current') })
  selectedProfile = 'current'
  const newPage = textContent(scopedPage())
  assert.match(newPage, /B-current/)
  assert.doesNotMatch(newPage, /A-private|A-late-private|only-on-A/)
}

// A null host connection is unresolved, not a cache identity shared by every
// unresolved remote. Neither cached payloads nor manually retried queries may
// cross that window, even when both request and current scope carry null.
activeConnection = null
activeHostProfile = 'default'
selectedProfile = 'default'
scopeResults.clear()
scopedSection()
scopedPage()
const unresolvedQueries = new Map(scopeQueries)
for (const query of unresolvedQueries.values()) {
  assert.equal(query.enabled, false)
  const callsBeforeRetry = scopedRestCalls
  await assert.rejects(query.queryFn(), /connection or active profile changed/)
  assert.equal(scopedRestCalls, callsBeforeRetry)
}
scopeResults.set('builtin-profiles', scoped({ profiles: [{ name: 'unresolved-private-option' }] }))
scopeResults.set('builtin', { profile: 'default', ...scoped(storesFor('unresolved-private-selected')) })
scopeResults.set('snapshot', scoped({ builtin: storesFor('unresolved-private-current') }))
assert.doesNotMatch(textContent(scopedSection()), /unresolved-private/)
selectedProfile = 'current'
assert.doesNotMatch(textContent(scopedPage()), /unresolved-private/)
activeConnection = 'gateway-c'
for (const query of unresolvedQueries.values()) {
  const callsBeforeRetry = scopedRestCalls
  await assert.rejects(query.queryFn(), /connection or active profile changed/)
  assert.equal(scopedRestCalls, callsBeforeRetry)
}
assert.doesNotMatch(textContent(scopedPage()), /unresolved-private/)
// A resolved request that loses its connection before completion is discarded.
const pendingSnapshot = scopeQueries.get('snapshot').queryFn()
activeConnection = null
pendingReads.shift().resolve({ builtin: storesFor('late-unresolved-private') })
await assert.rejects(pendingSnapshot, /connection or active profile changed/)
assert.doesNotMatch(textContent(scopedPage()), /unresolved-private/)
const connectionScopeChecks = {
  sameNameAcrossConnections: true,
  activeHostProfileChanges: true,
  currentSnapshotIsolated: true,
  obsoleteRequestsRejected: true,
  unresolvedConnectionsBlocked: true
}

process.stdout.write(JSON.stringify({
  builtinProfileChecks,
  connectionScopeChecks,
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
