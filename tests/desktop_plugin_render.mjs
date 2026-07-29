import fs from 'node:fs/promises'
import process from 'node:process'
import vm from 'node:vm'

const pluginPath = process.argv[2]
if (!pluginPath) throw new Error('preview plugin path is required')

const source = await fs.readFile(pluginPath, 'utf8')
const navigations = []
const restPaths = []
const automaticContentRequests = []
let effectRuns = 0
let localeBundles = null
let selectedCaseId = ''
let catalogIds = new Set()

function sdkComponent(name) {
  return function Component(props = {}) {
    if (name === 'EmptyState' || name === 'ErrorState') {
      return {
        type: `sdk:${name}`,
        props: { children: [props.title, props.description] }
      }
    }
    return { type: `sdk:${name}`, props }
  }
}

function translate(key, ...args) {
  const value = localeBundles?.en?.[key]
  if (typeof value === 'function') return value(...args)
  return value ?? key
}

const sdkValues = {
  Badge: sdkComponent('Badge'),
  Button: sdkComponent('Button'),
  EmptyState: sdkComponent('EmptyState'),
  ErrorState: sdkComponent('ErrorState'),
  GlyphSpinner: sdkComponent('GlyphSpinner'),
  Input: sdkComponent('Input'),
  PALETTE_AREA: 'palette.commands',
  ROUTES_AREA: 'routes',
  Select: sdkComponent('Select'),
  SelectContent: sdkComponent('SelectContent'),
  SelectItem: sdkComponent('SelectItem'),
  SelectTrigger: sdkComponent('SelectTrigger'),
  SelectValue: sdkComponent('SelectValue'),
  Separator: sdkComponent('Separator'),
  SIDEBAR_NAV_AREA: 'sidebar.nav',
  Skeleton: sdkComponent('Skeleton'),
  Textarea: sdkComponent('Textarea'),
  host: {
    navigate: path => navigations.push(path),
    notify: () => {},
    notifyError: () => {}
  },
  icons: {},
  useMutation: ({ mutationFn }) => {
    const data = mutationFn({ query: 'fixture query', search: 'fixture', limit: 25 })
    if (data && typeof data.then === 'function') {
      throw new Error('preview mutation unexpectedly returned a Promise')
    }
    return {
      mutate: value => {
        automaticContentRequests.push(value)
        return mutationFn(value)
      },
      isPending: false,
      error: null,
      data
    }
  },
  usePluginI18n: () => translate,
  useQuery: ({ queryFn }) => {
    const data = queryFn()
    if (data && typeof data.then === 'function') {
      throw new Error('preview query unexpectedly returned a Promise')
    }
    return { data, isLoading: false, error: null, refetch: () => {} }
  },
  useQueryClient: () => ({ invalidateQueries: () => {} })
}

const reactValues = {
  Fragment: Symbol.for('react.fragment'),
  useEffect: fn => {
    effectRuns += 1
    fn()
  },
  useMemo: fn => fn(),
  useState: initial => [
    typeof initial === 'string' && catalogIds.has(initial) ? selectedCaseId : initial,
    () => {}
  ]
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
const catalog = module.namespace.PREVIEW_CATALOG
if (!plugin || typeof plugin.register !== 'function') {
  throw new Error('preview plugin must default-export a registerable plugin')
}
if (!catalog?.development_only || !Array.isArray(catalog.cases) || !catalog.cases.length) {
  throw new Error('preview plugin must embed a non-empty development catalog')
}
catalogIds = new Set(catalog.cases.map(item => item.id))

const contributions = []
const ctx = {
  i18n: {
    register: bundles => {
      localeBundles = bundles
      return () => {}
    },
    t: key => ({ title: 'Memory', openMemory: 'Open Memory' })[key] ?? key
  },
  register: contribution => {
    contributions.push(contribution)
    return () => {}
  },
  registerMany: values => {
    contributions.push(...values)
    return () => {}
  },
  rest: async path => {
    restPaths.push(path)
    throw new Error(`preview attempted a live REST call: ${path}`)
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
if (!route || !sidebar || !palette) throw new Error('missing preview route, sidebar, or palette contribution')

function renderText(node, path = 'root', output = []) {
  if (node === null || node === undefined || typeof node === 'boolean') return output
  if (Array.isArray(node)) {
    node.forEach((child, index) => renderText(child, `${path}[${index}]`, output))
    return output
  }
  if (typeof node === 'string' || typeof node === 'number') {
    output.push(String(node))
    return output
  }
  if (typeof node !== 'object' || !('type' in node)) return output

  if (node.type === runtimeValues.Fragment) {
    return renderText(node.props?.children, `${path}.Fragment`, output)
  }
  if (typeof node.type === 'function') {
    const name = node.type.name || 'AnonymousComponent'
    let rendered
    try {
      rendered = node.type(node.props ?? {})
    } catch (error) {
      throw new Error(`render failed at ${path}.${name}: ${error?.stack || error}`)
    }
    return renderText(rendered, `${path}.${name}`, output)
  }
  return renderText(node.props?.children, `${path}.${String(node.type)}`, output)
}

const providerLabels = [
  'Holographic memory',
  'Mem0 memory',
  'Honcho memory',
  'Mnemosyne memory',
  'Hindsight memory',
  'ByteRover memory'
]
const renderedCases = []
for (const fixture of catalog.cases) {
  selectedCaseId = fixture.id
  const text = renderText(route.render()).join('\n')
  for (const label of providerLabels) {
    if (!text.includes(label)) {
      throw new Error(`fixture ${fixture.id} did not render provider label: ${label}`)
    }
  }
  for (const expected of fixture.assertions ?? []) {
    if (!text.includes(expected)) {
      throw new Error(`fixture ${fixture.id} did not render expected text: ${expected}`)
    }
  }
  renderedCases.push({
    id: fixture.id,
    assertionCount: fixture.assertions?.length ?? 0,
    textLength: text.length
  })
}

palette.data.run()
if (restPaths.length) {
  throw new Error(`preview made live REST calls: ${restPaths.join(', ')}`)
}

process.stdout.write(JSON.stringify({
  automaticContentRequests,
  catalogSource: catalog.source,
  cases: renderedCases,
  effectRuns,
  navigation: navigations.at(-1),
  plugin: { id: plugin.id, name: plugin.name },
  restPaths,
  route: route.data.path,
  sidebar: { path: sidebar.data.path, label: sidebar.data.label }
}))
