import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import vm from 'node:vm'

const source = await fs.readFile(process.argv[2], 'utf8')
const requests = []
let registered
let states = []
let effects = []
let index = 0
let queued = []
const snapshot = { builtin: { stores: [], total_entries: 0, hermes_home: '/active' } }
const hooks = {
  useState(initial) {
    const slot = index++
    if (!(slot in states)) states[slot] = initial
    return [states[slot], value => {
      states[slot] = typeof value === 'function' ? value(states[slot]) : value
    }]
  },
  useMemo: fn => fn(),
  useEffect(fn, deps) {
    const slot = index++
    const previous = effects[slot]
    if (!previous || deps.some((value, i) => value !== previous.deps[i])) {
      queued.push(() => {
        previous?.cleanup?.()
        effects[slot] = { deps, cleanup: fn() }
      })
    }
  }
}
const window = {
  location: { search: '?profile=host-bot' },
  __HERMES_PLUGIN_SDK__: {
    React: { Fragment: 'fragment', createElement: (type, props, ...children) => ({ type, props: { ...props, children } }) },
    hooks,
    components: new Proxy({}, { get: (_target, key) => key }),
    fetchJSON(url) {
      return new Promise((resolve, reject) => requests.push({ url, resolve, reject }))
    }
  },
  __HERMES_PLUGINS__: { register: (_name, page) => { registered = page } }
}
vm.runInNewContext(source, { window, URLSearchParams, setTimeout, Date, Math, Number, String, Promise })
function walk(node, predicate) {
  if (!node || typeof node !== 'object') return null
  if (Array.isArray(node)) return node.map(child => walk(child, predicate)).find(Boolean)
  if (predicate(node)) return node
  return walk(node.props?.children, predicate)
}
// Capture the actual nested component without exposing test-only exports.
states[0] = snapshot
const page = registered()
const browserNode = walk(page, node => node.type?.name === 'BuiltinProfileBrowser')
assert.ok(browserNode)
const Browser = browserNode.type
states = []
effects = []
queued = []
function render() {
  index = 0
  const tree = Browser(browserNode.props)
  queued.splice(0).forEach(effect => effect())
  return tree
}
async function flush() { await new Promise(resolve => setTimeout(resolve, 0)); await Promise.resolve() }
function change(tree, name) {
  walk(tree, node => node.type === 'select').props.onChange({ target: { value: name } })
  return render()
}
function shownBuiltin(tree) {
  return walk(tree, node => node.type?.name === 'BuiltinSection')?.props.builtin
}
function latestMemoryRequest() {
  return requests.filter(request => new URL(request.url, 'http://test').pathname.endsWith('/builtin')).at(-1)
}
let tree = render()
assert.equal(shownBuiltin(tree).hermes_home, '/active')
await flush()
requests[0].resolve({ profiles: [
  { name: 'current', label: 'Active profile' },
  { name: 'default', label: 'default' },
  { name: 'alpha', label: 'Alpha bot' },
  { name: 'beta', label: 'Beta bot' }
] })
await flush()
tree = render()
const select = walk(tree, node => node.type === 'select')
assert.equal(select.props.children[0].length, 4)
tree = change(tree, 'alpha')
assert.equal(shownBuiltin(tree), undefined, 'active files must disappear during selection')
await flush()
const alpha = latestMemoryRequest()
assert.equal(new URL(alpha.url, 'http://test').searchParams.get('memory_profile'), 'alpha')
assert.equal(new URL(alpha.url, 'http://test').searchParams.get('profile'), 'host-bot')
tree = change(tree, 'beta')
await flush()
alpha.resolve({ hermes_home: '/alpha', stores: [] })
await flush()
tree = render()
assert.equal(shownBuiltin(tree), undefined, 'late alpha response must not paint beta')
latestMemoryRequest().resolve({ hermes_home: '/beta', stores: [] })
await flush()
tree = render()
assert.equal(shownBuiltin(tree).hermes_home, '/beta')
const beforeSnapshotRefresh = requests.length
browserNode.props.builtin = { ...snapshot.builtin, generated_at: 2 }
tree = render()
await flush()
assert.equal(requests.length, beforeSnapshotRefresh, 'unrelated snapshot refresh must not reload another bot')
assert.equal(shownBuiltin(tree).hermes_home, '/beta')
walk(tree, node => node.type === 'Button').props.onClick()
tree = render()
await flush()
requests.filter(request => request.url.includes('/builtin/profiles')).at(-1).resolve({
  profiles: [{ name: 'current', label: 'Active profile' }]
})
latestMemoryRequest().reject(new Error('Profile beta disappeared'))
await flush()
tree = render()
const missingSelector = walk(tree, node => node.type === 'select')
assert.equal(missingSelector.props.value, 'beta')
assert.ok(walk(missingSelector, node => node.type === 'option' && node.props.value === 'beta'
  && node.props.children[0] === 'beta (unavailable)'))
assert.ok(walk(missingSelector, node => node.type === 'option' && node.props.value === 'current'))
assert.equal(shownBuiltin(tree), undefined, 'deleted profile must not retain old files')
tree = change(tree, 'default')
await flush()
latestMemoryRequest().reject(new Error('Profile disappeared'))
await flush()
tree = render()
assert.equal(shownBuiltin(tree), undefined, 'failure must not retain beta files')
assert.ok(walk(tree, node => node.props?.error === 'Profile disappeared'))
tree = change(tree, 'current')
assert.equal(shownBuiltin(tree).hermes_home, '/active')
walk(tree, node => node.type === 'Button').props.onClick()
tree = render()
await flush()
latestMemoryRequest().resolve({ hermes_home: '/active-refreshed', stores: [] })
await flush()
tree = render()
assert.equal(shownBuiltin(tree).hermes_home, '/active-refreshed')
walk(tree, node => node.type === 'Button').props.onClick()
tree = render()
await flush()
latestMemoryRequest().reject(new Error('Refresh temporarily failed'))
await flush()
tree = render()
assert.equal(shownBuiltin(tree), undefined)
browserNode.props.builtin = { ...snapshot.builtin, hermes_home: '/active-newer' }
tree = render()
assert.equal(shownBuiltin(tree).hermes_home, '/active-newer', 'fresh snapshot must supersede a failed current refresh')
assert.ok(!walk(tree, node => node.props?.error === 'Refresh temporarily failed'))
tree = change(tree, 'alpha')
await flush()
const changedHostRequest = latestMemoryRequest()
window.location.search = '?profile=another-host-bot'
changedHostRequest.resolve({ hermes_home: '/alpha', stores: [] })
await flush()
tree = render()
assert.equal(shownBuiltin(tree), undefined)
assert.ok(walk(tree, node => node.props?.error?.includes('host profile changed')),
  'stale host reply must expose a refresh action rather than loading forever')
assert.equal(requests.every(request => new URL(request.url, 'http://test').searchParams.get('profile') === 'host-bot'), true)
console.log('Dashboard builtin profile selection: ok')
