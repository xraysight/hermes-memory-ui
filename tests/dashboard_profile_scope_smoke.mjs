import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import process from 'node:process'
import vm from 'node:vm'

const pluginPath = process.argv[2]
if (!pluginPath) throw new Error('dashboard plugin path is required')
const source = await fs.readFile(pluginPath, 'utf8')

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, reject, resolve }
}

function makeHarness(initialSearch, options = {}) {
  const requests = []
  const stateWrites = []
  let registered = null
  let renderLabel = ''
  let hookIndex = 0

  const hooks = {
    useEffect: effect => effect(),
    useMemo: fn => fn(),
    useState: initial => {
      const index = hookIndex++
      let value = typeof initial === 'function' ? initial() : initial
      if (options.initialSnapshot && index === 0 && value === null) value = options.initialSnapshot
      if (options.defaultText && value === '') value = options.defaultText
      return [value, next => stateWrites.push({ index, label: renderLabel, value: next })]
    }
  }
  const identityComponent = props => props
  const components = options.renderTree
    ? new Proxy({}, { get: (_target, name) => String(name) })
    : new Proxy({}, { get: () => identityComponent })
  const window = {
    location: { search: initialSearch },
    __HERMES_PLUGIN_SDK__: {
      React: {
        Fragment: Symbol.for('react.fragment'),
        createElement: (type, props, ...children) => {
          const node = { type, props: { ...(props ?? {}), children } }
          return options.renderTree && typeof type === 'function' ? type(node.props) : node
        }
      },
      hooks,
      components,
      fetchJSON: url => {
        const pending = deferred()
        requests.push({ pending, url })
        return pending.promise
      }
    },
    __HERMES_PLUGINS__: {
      register: (_name, component) => { registered = component }
    }
  }
  const context = vm.createContext({
    Date,
    Math,
    Number,
    Promise,
    String,
    URLSearchParams,
    console,
    setTimeout,
    window
  })
  vm.runInContext(source, context, { filename: pluginPath })
  assert.equal(typeof registered, 'function', 'dashboard plugin did not register a page')

  return {
    requests,
    stateWrites,
    window,
    render(label) {
      renderLabel = label
      hookIndex = 0
      return registered()
    }
  }
}

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

// A first visit via a bare sidebar link has no previously observed profile.
// The host's parent effect restores the selection after the child effect.
const firstVisit = makeHarness('')
firstVisit.render('first-visit')
firstVisit.window.location.search = '?profile=beta'
await flushPromises()
assert.equal(new URL(firstVisit.requests[0].url, 'http://test').searchParams.get('profile'), 'beta',
  'the first visit requested the launch profile before the parent synchronized the URL')

const scoped = makeHarness('?profile=alpha')
scoped.render('alpha')
await flushPromises()
assert.equal(
  scoped.requests[0].url,
  '/api/plugins/hermes-memory-ui/snapshot?limit=500&min_trust=0&profile=alpha'
)

// Select beta while the plugin is unmounted, then re-enter through a bare
// sidebar URL. A cached "last profile" would incorrectly request alpha.
scoped.window.location.search = ''
scoped.render('re-entry-after-unmounted-selection')
scoped.window.location.search = '?profile=beta'
await flushPromises()
assert.equal(
  scoped.requests[1].url,
  '/api/plugins/hermes-memory-ui/snapshot?limit=500&min_trust=0&profile=beta'
)

// A later selector change wins immediately, and an alpha response that
// arrives afterwards must not publish alpha data into the beta view.
scoped.window.location.search = '?profile=beta'
scoped.render('beta')
await flushPromises()
assert.equal(
  scoped.requests[2].url,
  '/api/plugins/hermes-memory-ui/snapshot?limit=500&min_trust=0&profile=beta'
)
scoped.requests[0].pending.resolve({ marker: 'stale-alpha' })
await flushPromises()
assert.equal(
  scoped.stateWrites.some(write => write.index === 0 && write.value?.marker === 'stale-alpha'),
  false,
  'a stale profile response reached snapshot state'
)
scoped.requests[2].pending.resolve({ marker: 'fresh-beta' })
await flushPromises()
assert.equal(
  scoped.stateWrites.some(write => write.index === 0 && write.value?.marker === 'fresh-beta'),
  true,
  'the current profile response did not reach snapshot state'
)

for (const explicit of ['current', 'default']) {
  const harness = makeHarness(`?profile=${explicit}`)
  harness.render(explicit)
  await flushPromises()
  assert.equal(new URL(harness.requests[0].url, 'http://test').searchParams.get('profile'), explicit)
}

const legacy = makeHarness('')
legacy.render('legacy')
await flushPromises()
assert.equal(new URL(legacy.requests[0].url, 'http://test').searchParams.has('profile'), false)

// Render every configured provider section and invoke its real click handlers.
// This exercises request behavior rather than matching endpoint strings in the
// bundle source.
const snapshot = {
  generated_at: 1,
  builtin: { hermes_home: '/synthetic', stores: [], total_entries: 0 },
  holographic: { provider_configured: true, facts: [], total_facts: 0 },
  mem0: { provider_configured: true, memories: [], total_memories: 0 },
  honcho: {
    provider_configured: true,
    user: { card: [], conclusions: [] },
    ai: { card: [], conclusions: [] },
    search_results: []
  },
  mnemosyne: { provider_configured: true, memories: [], facts: [], db_exists: false },
  hindsight: { provider_configured: true, memories: [], documents: [] },
  byterover: { provider_configured: true, locations: [], results: [], project_exists: true }
}
const everyPath = makeHarness('?profile=alpha', {
  defaultText: 'probe',
  initialSnapshot: snapshot,
  renderTree: true
})
const tree = everyPath.render('all-paths')

function textContent(value) {
  if (value === null || value === undefined || value === false) return ''
  if (typeof value !== 'object') return String(value)
  if (Array.isArray(value)) return value.map(textContent).join('')
  return textContent(value.props?.children)
}

function visit(value, callback) {
  if (!value || typeof value !== 'object') return
  if (Array.isArray(value)) {
    value.forEach(item => visit(item, callback))
    return
  }
  callback(value)
  visit(value.props?.children, callback)
}

const actionLabels = new Set([
  'Search sessions',
  'Run query',
  'Recall',
  'Reflect',
  'Preview inject',
  'Refresh contents'
])
visit(tree, node => {
  const label = textContent(node)
  if (node.type === 'Button' && actionLabels.has(label) && typeof node.props.onClick === 'function') {
    node.props.onClick()
  }
})

await flushPromises()
const exercisedPaths = new Set(
  everyPath.requests.map(request => new URL(request.url, 'http://test').pathname)
)
assert.deepEqual(
  [...exercisedPaths].sort(),
  [
    '/api/plugins/hermes-memory-ui/byterover/query',
    '/api/plugins/hermes-memory-ui/hindsight/contents',
    '/api/plugins/hermes-memory-ui/hindsight/recall',
    '/api/plugins/hermes-memory-ui/hindsight/reflect',
    '/api/plugins/hermes-memory-ui/mnemosyne/contents',
    '/api/plugins/hermes-memory-ui/mnemosyne/prefetch',
    '/api/plugins/hermes-memory-ui/mnemosyne/recall',
    '/api/plugins/hermes-memory-ui/session-search',
    '/api/plugins/hermes-memory-ui/snapshot'
  ]
)
assert.equal(
  everyPath.requests.every(request => new URL(request.url, 'http://test').searchParams.get('profile') === 'alpha'),
  true,
  'at least one dashboard request path did not follow the selected profile'
)

process.stdout.write(JSON.stringify({
  exercisedRequestPaths: [...exercisedPaths].sort(),
  firstEntryProfile: 'beta',
  legacyProfileOmitted: true,
  reentryProfile: 'beta',
  staleResponseSuppressed: true
}))
