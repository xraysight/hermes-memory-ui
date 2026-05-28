# Hermes Memory UI Plugin

Dashboard plugin for inspecting [Hermes Agent](https://github.com/NousResearch/hermes-agent) memory.

Current scope:

- Built-in memory:
  * `MEMORY.md` — agent notes / environment facts / project conventions
  * `USER.md` — user profile / preferences
- Session search:
  * explicit read-only search over previous Hermes sessions via Hermes' `session_search` tool
  * optional source/type filter such as CLI, Telegram, cron, Discord, web, or API sessions
- External memory providers:
  * Holographic memory:
    + local SQLite fact store, default: `$HERMES_HOME/memory_store.db`
    + facts, categories, trust scores, retrieval counters, timestamps
  * Mem0 memory:
    + read-only Mem0 Platform memories via Hermes' `mem0` provider config
    + memories, user/agent scope, scores returned by search, timestamps, metadata
  * Honcho memory:
    + read-only Honcho workspace, host, peer, and provider configuration state
    + user/AI peer cards, representations, conclusions, and context search
  * Mnemosyne memory:
    + read-only local SQLite store inspection for episodes, facts, instructions, gists, and graph rows
    + explicit recall and injected-context preview through the Hermes Mnemosyne provider
  * Hindsight memory:
    + read-only/query-only Hindsight provider configuration state
    + explicit recall and reflect actions; no automatic retain/write flow
    + contents view via the official Hindsight client for memory units and retained source documents
  * ByteRover memory:
    + read-only ByteRover CLI (`brv`) project status and registered locations
    + explicit BM25 search and optional query/synthesis action; no curate/write flow

This plugin is intentionally read-only. It does not add, edit, replace, or remove memories. That is deliberate: writes should go through Hermes' `memory` and `fact_store` tools or provider classes so validation, locking, mirroring, FTS, HRR vectors, and memory-bank maintenance are preserved.

## Screenshots

Built-in memory view:

![Hermes Memory UI built-in memory view](docs/assets/hermes-memory-dashboard1.png)

Holographic memory view:

![Hermes Memory UI holographic memory view](docs/assets/hermes-memory-dashboard2.png)

Mem0 memory view:

![Hermes Memory UI Mem0 memory view](docs/assets/hermes-memory-dashboard3.png)

Honcho memory view:

![Hermes Memory UI Honcho memory view](docs/assets/hermes-memory-dashboard4.png)

Hindsight memory view:

![Hermes Memory UI Hindsight memory view](docs/assets/hermes-memory-dashboard5.png)

Mnemosyne memory view:

![Hermes Memory UI Mnemosyne memory view](docs/assets/hermes-memory-dashboard7.png)

Byterover memory view:

![Hermes Memory UI Byterover memory view](docs/assets/hermes-memory-dashboard6.png)

## Requirements

- Hermes Agent with web dashboard support.
- Dashboard plugin support as documented at:
  `https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard`
- Optional: external memory provider enabled.

The built-in memory view works always, while external memory provider sections are shown only when configured.

## Installation

### Install directly from GitHub

```bash
hermes plugins install xraysight/hermes-memory-ui --enable
```

### Update existing installation

```bash
hermes plugins update hermes-memory-ui
```

### Install from a local checkout

From this repository directory:

```bash
mkdir -p "${HERMES_HOME:-$HOME/.hermes}/plugins/hermes-memory-ui"
cp -R dashboard "${HERMES_HOME:-$HOME/.hermes}/plugins/hermes-memory-ui/"
```

### Reload the dashboard

If the dashboard is already running, force plugin discovery:

```bash
curl http://127.0.0.1:9119/api/dashboard/plugins/rescan
```

Then refresh the browser. A new `Memory` tab should appear.

If the plugin API route returns 404 after installing, restart the dashboard. Hermes mounts plugin backend routes at dashboard startup.

```bash
hermes dashboard
```

or stop/start your existing dashboard process/service.

## What the UI shows

Top summary:

- built-in entry count
- active Hermes home
- snapshot generation time
- holographic total fact count only when `memory.provider` is currently `holographic`
- Mem0 memory count only when `memory.provider` is currently `mem0`
- Honcho peer-card fact count only when `memory.provider` is currently `honcho`
- Mnemosyne episode count only when `memory.provider` is currently `mnemosyne`
- Hindsight bank/status only when `memory.provider` is currently `hindsight`
- ByteRover registered location count only when `memory.provider` is currently `byterover`

Built-in memory section:

- Agent memory card (`MEMORY.md`)
- User profile card (`USER.md`)
- path, file existence, modification time
- entry count and char usage bar
- parsed entries

Session search section:

- explicit query box for previous Hermes sessions
- optional session type/source filter
- newest-first results with snippets and short message context
- no automatic search on page load and no memory writes

Holographic memory section, displayed only when `memory.provider` is currently `holographic`:

- DB existence
- whether `memory.provider` is currently `holographic`
- total facts
- facts shown after filters
- entity count
- memory bank count
- filters for search, category, min trust, and limit; click `Apply / refresh` to run them
- fact cards with category, trust score, counters, content, tags, timestamps

Mem0 memory section, displayed when `memory.provider` is currently `mem0`:

- whether Mem0 is the active provider
- whether an API key is present and configured `user_id` and `agent_id`
- memories returned by `get_all()` or `search()` after clicking `Apply / refresh` button
- memory cards with score, user/agent scope, content, timestamps, and metadata

Honcho memory section, displayed when `memory.provider` is currently `honcho`:

- whether Honcho is the active provider
- resolved host, workspace, user peer, AI peer, recall mode, and session strategy
- whether an API key or self-hosted/base URL is configured, without exposing secrets
- user and AI peer cards
- user and AI representations
- conclusions returned for user and AI peers
- context search after clicking `Apply / refresh` button

Mnemosyne memory section, displayed when `memory.provider` is currently `mnemosyne`:

- whether Mnemosyne is the active provider
- local data directory and SQLite DB path
- table counts for episodic memory, Memoria facts/instructions/preferences/timelines, gists, triples, and vector row indexes
- memory and fact cards from the local SQLite store, with search and limit filters
- explicit `Recall` query button for ranked memory retrieval through Hermes' Mnemosyne provider
- explicit `Preview inject` button for the exact prefetch/auto-inject context returned by the provider
- no remember/sleep/update/forget/import/export endpoint

Hindsight memory section, displayed when `memory.provider` is currently `hindsight`:

- whether Hindsight is the active provider
- resolved mode, bank, budget, memory mode, and auto-retain/auto-recall flags
- whether API/LLM keys are present, without exposing secrets
- explicit `Recall` query button for ranked memory retrieval
- explicit `Reflect` query button for synthesis over memories
- automatically displayed Hindsight contents with a `Refresh` button for extracted memory units plus retained source documents
- no retain/write endpoint

ByteRover memory section, displayed when `memory.provider` is currently `byterover`:

- whether ByteRover is the active provider
- whether the `brv` CLI is available
- configured project root and optional search scope
- registered ByteRover locations
- explicit BM25 `Search / refresh` action through `brv search --format json`
- explicit `Run query` action through `brv query --format json`
- no `curate`, `review approve`, version-control, sync, or write endpoints

## Holographic DB path resolution

The plugin reads the DB path from:

```yaml
plugins:
  hermes-memory-store:
    db_path: ...
```

If not configured, it falls back to:

```text
$HERMES_HOME/memory_store.db
```

`$HERMES_HOME`, `${HERMES_HOME}`, and `~` are expanded.

The SQLite connection is opened in read-only mode using `mode=ro`.

## Mem0 configuration

Mem0 support follows Hermes' bundled `mem0` memory provider convention:

- put secrets in `$HERMES_HOME/.env`, especially `MEM0_API_KEY`
- put non-secret Mem0 scope/config in `$HERMES_HOME/mem0.json`

Example `$HERMES_HOME/.env`:

```bash
MEM0_API_KEY=your-key
```

Example `$HERMES_HOME/mem0.json`:

```json
{
  "user_id": "hermes-user",
  "agent_id": "hermes",
  "rerank": true
}
```

Environment values also supported by Hermes' provider:

- `MEM0_API_KEY`
- `MEM0_USER_ID`
- `MEM0_AGENT_ID`
- `MEM0_RERANK`

`mem0.json` may technically override these values if fields are present, matching Hermes' provider behavior, but keeping `api_key` in `.env` is the recommended safer layout. The API key is only used server-side to instantiate `mem0.MemoryClient`; it is never returned in plugin responses.
The plugin performs read-only calls:

- `client.get_all(filters={"user_id": ...})` when no search query is provided
- `client.search(query=..., filters={"user_id": ...}, rerank=..., top_k=...)` when search is provided

## Honcho configuration

Honcho support follows Hermes' bundled `honcho` memory provider convention and reuses Hermes' provider helpers for config resolution and client creation. Supported config locations are resolved by Hermes, including:

- `$HERMES_HOME/honcho.json`
- `~/.hermes/honcho.json`
- `~/.honcho/config.json`
- environment variables such as `HONCHO_API_KEY`, `HONCHO_BASE_URL`, and `HONCHO_ENVIRONMENT`

Honcho is a workspace/peer/session memory system rather than a flat memory list. The dashboard therefore shows peer cards, representations, conclusions, and context search rather than claiming a complete list of all memories. The API key is only used server-side through Hermes' Honcho provider helpers; it is never returned in plugin responses.

The plugin performs read-only calls such as:

- `HonchoClientConfig.from_global_config()` and `get_honcho_client(...)`
- `client.peer(...)` for user and AI peers
- `peer.context(target=..., search_query=..., search_top_k=...)`
- `peer.representation(...)` or peer card fallbacks when needed
- `peer.conclusions_of(target).list(...)`

It does not call Honcho dialectic reasoning (`peer.chat()` / `honcho_reasoning`) automatically from page load or `/snapshot`.

## Mnemosyne configuration

Mnemosyne support follows Hermes' Mnemosyne memory provider convention. The plugin reads non-secret state from:

- `memory.provider: mnemosyne` in `$HERMES_HOME/config.yaml`
- `$HERMES_HOME/mnemosyne/data/mnemosyne.db` by default
- optional `memory.mnemosyne.data_dir` / `memory.mnemosyne.db_path`
- optional environment variables such as `MNEMOSYNE_DATA_DIR`, `MNEMOSYNE_DB_PATH`, `MNEMOSYNE_PREFETCH_CONTENT_CHARS`, and `MNEMOSYNE_AUTO_SLEEP_ENABLED`

The SQLite connection is opened in read-only mode using `mode=ro`. The dashboard reads ordinary text tables such as `episodic_memory`, `memoria_facts`, `memoria_instructions`, `memoria_preferences`, `memoria_timelines`, `gists`, and `triples`. It deliberately does not query sqlite-vec virtual tables directly; it only counts their rowid side tables when present so the UI works without loading sqlite-vec into the dashboard process.

The plugin performs query-only provider calls:

- `MnemosyneMemoryProvider.initialize(...)`
- `provider.handle_tool_call("mnemosyne_recall", ...)` for explicit recall
- `provider.prefetch(...)` for injected-context preview

It does not expose `mnemosyne_remember`, `mnemosyne_sleep`, `mnemosyne_update`, `mnemosyne_forget`, `mnemosyne_import`, or any other write/maintenance tool.

## Hindsight configuration

Hindsight support follows Hermes' bundled `hindsight` memory provider convention. The plugin reads non-secret configuration from:

- `$HERMES_HOME/hindsight/config.json`
- legacy `~/.hindsight/config.json`
- environment variables such as `HINDSIGHT_MODE`, `HINDSIGHT_API_URL`, `HINDSIGHT_DAEMON_URL`, `HINDSIGHT_BANK_ID`, and `HINDSIGHT_BUDGET`

The daemon/API endpoint is resolved with this precedence:

```text
hindsight/config.json api_url > HINDSIGHT_API_URL > HINDSIGHT_DAEMON_URL > default
```

For `local_embedded`, the default endpoint is `http://localhost:8888`. If the resolved endpoint is remote, for example `HINDSIGHT_DAEMON_URL=http://192.168.42.20:8888`, the dashboard treats that daemon as authoritative and does not try to start `hindsight-embed daemon start` on the dashboard host. Local daemon startup is attempted only for `localhost`, `127.0.0.1`, or `::1` endpoints.

When local daemon startup is needed, the plugin resolves `hindsight-embed` from `PATH`, the current Python environment, Hermes' bundled venv under `$HERMES_HOME/hermes-agent/venv/bin`, the default `~/.hermes/hermes-agent/venv/bin`, or `~/.local/bin`. If the binary cannot be found, the error includes safe diagnostics for `PATH`, `sys.executable`, and checked paths.

Secrets such as `HINDSIGHT_API_KEY` and `HINDSIGHT_LLM_API_KEY` are only detected as boolean `*_present` flags and are never returned in plugin responses. Hindsight is query-oriented rather than a complete list API, so the dashboard only calls recall/reflect after the user clicks a button. `/snapshot` and page load include status/config only.

The plugin performs read-only/query-only calls through Hermes' Hindsight provider internals and the official `hindsight_client` SDK:

- `HindsightMemoryProvider.initialize(...)`
- `client.arecall(...)` for explicit recall
- `client.areflect(...)` for explicit reflection
- `Hindsight(...).memory.list_memories(...)` for visible memory units
- `Hindsight(...).documents.list_documents(...)` and `get_document(...)` for retained source documents
- `Hindsight(...).banks.get_agent_stats(...)` for bank counts/status

Recall and reflect show only native Hindsight results. Retained source documents are displayed separately in the contents view; they are not used as a fallback for recall or reflect.

It does not expose `hindsight_retain` or any write UI.

## ByteRover configuration

ByteRover support uses the local `brv` CLI. The plugin reads non-secret configuration from `$HERMES_HOME/byterover.json`, from `plugins.hermes-memory-ui.byterover` in Hermes config, or from environment variables.

Example `$HERMES_HOME/byterover.json`:

```json
{
  "brv_path": "brv",
  "project_root": "/path/to/project",
  "search_scope": "docs/",
  "query_timeout": 60
}
```

Environment values:

- `BRV_PATH`
- `BYTEROVER_PROJECT_ROOT`
- `BYTEROVER_SEARCH_SCOPE`
- `BYTEROVER_QUERY_TIMEOUT`

The plugin performs read-only/query-only CLI calls:

- `brv locations --format json`
- `brv status --format json [--project-root ...]`
- `brv search QUERY --format json --limit N [--scope ...]`
- `brv query QUERY --format json --timeout N` only after the user clicks `Run query`

It does not expose `brv curate`, `brv review approve`, version-control, push/pull, sync, or other mutation commands.

## API endpoints

Hermes mounts this plugin under:

```text
/api/plugins/hermes-memory-ui/
```

Available API endpoints:

### GET `/status`

Returns plugin status, active Hermes home, configured memory provider, built-in memory paths, holographic DB path, Mem0 configuration status, Honcho configuration status, Mnemosyne configuration status, Hindsight configuration status, and ByteRover CLI/configuration status.

Example:

```bash
curl http://127.0.0.1:9119/api/plugins/hermes-memory-ui/status | jq
```

### GET `/builtin`

Returns parsed built-in memory stores:

- `memory` from `$HERMES_HOME/memories/MEMORY.md`
- `user` from `$HERMES_HOME/memories/USER.md`

Entries are split on Hermes' built-in delimiter §.

The response includes entry count, char count, configured/default char limits, usage percentage, file path, and modified timestamp.

### GET `/session-search`

Runs an explicit read-only search over previous Hermes sessions through Hermes' built-in `session_search` tool. This endpoint is not called from `/snapshot` or page load; the UI calls it only after the user submits a query.

Query parameters:

- `query`: required search query
- `limit`: 1-10, default 3
- `sort`: `newest` or `oldest`, default `newest`
- `source`: optional exact source/type filter, e.g. `cli`, `telegram`, `cron`, `discord`, `web`, or `api`

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/session-search?query=dashboard&limit=3&sort=newest' | jq
```

### GET `/holographic`

Returns facts from holographic SQLite memory.

Query parameters:

- `limit`: 1-2000, default 500
- `category`: optional category filter, e.g. `user_pref`, `project`, `tool`, `general`
- `min_trust`: 0.0-1.0, default 0.0
- `search`: optional substring search over `content` and `tags`

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/holographic?limit=100&min_trust=0.3' | jq
```

### GET `/mem0`

Returns read-only memories from the Mem0 Platform API.

Query parameters:

- `limit`: 1-2000, default 500
- `search`: optional search query; uses Mem0 semantic search

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/mem0?limit=100&search=dashboard' | jq
```

### GET `/honcho`

Returns read-only Honcho provider state, user/AI peer cards, representations, conclusions, and optional context search.

Query parameters:

- `limit`: 1-100, default 50
- `search`: optional context search query

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/honcho?limit=25&search=dashboard' | jq
```

### GET `/mnemosyne`

Returns Mnemosyne provider status plus read-only local store contents.

### GET `/mnemosyne/contents`

Lists Mnemosyne local SQLite memory and fact rows. This is read-only.

Query parameters:

- `search`: optional text filter applied to visible memory/fact text and metadata columns
- `limit`: optional, defaults to 25, capped at 100

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/mnemosyne/contents?search=dashboard&limit=25' | jq
```

### GET `/mnemosyne/recall`

Runs explicit Mnemosyne recall through the Hermes provider.

Query parameters:

- `query`: required query string
- `limit`: 1-100, default 25
- `temporal_weight`: 0.0-1.0, default 0.2

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/mnemosyne/recall?query=dashboard&limit=25&temporal_weight=0.2' | jq
```

### GET `/mnemosyne/prefetch`

Returns the injected-context preview generated by Mnemosyne prefetch.

Query parameters:

- `query`: required query string

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/mnemosyne/prefetch?query=dashboard' | jq
```

### GET `/byterover`

Returns read-only ByteRover CLI status, registered locations, and optional BM25 search results.

Query parameters:

- `limit`: 1-50, default 10
- `search`: optional search query; uses `brv search --format json`

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/byterover?limit=10&search=dashboard' | jq
```

### GET `/byterover/query`

Runs explicit ByteRover query/synthesis. This may invoke ByteRover's configured model; it is never called automatically on page load.

Query parameters:

- `query`: required question string
- `timeout`: 1-300 seconds, default 60

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/byterover/query?query=dashboard&timeout=60' | jq
```

### GET `/hindsight`

Returns Hindsight provider status/config only. It does not run recall or reflect.

### GET `/hindsight/contents`

Lists Hindsight memory units and retained source documents through the official `hindsight_client` SDK. This is read-only. The UI loads it for the Hindsight section and also provides a manual `Refresh contents` action.

Query parameters:

- `search`: optional text filter applied to memory/document text, IDs, tags, and metadata
- `limit`: optional, defaults to 25, capped at 100

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/hindsight/contents?search=dashboard&limit=25' | jq
```

### GET `/hindsight/recall`

Runs explicit Hindsight recall.

Query parameters:

- `query`: required query string
- `limit`: 1-100, default 25

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/hindsight/recall?query=dashboard&limit=25' | jq
```

### GET `/hindsight/reflect`

Runs explicit Hindsight reflect/synthesis.

Query parameters:

- `query`: required query string

Example:

```bash
curl 'http://127.0.0.1:9119/api/plugins/hermes-memory-ui/hindsight/reflect?query=dashboard' | jq
```

### GET `/snapshot`

Combined payload used by the UI. Accepts the same query parameters as `/holographic`; `limit` and `search` are also applied to Mem0, Honcho, Mnemosyne, and ByteRover, with Honcho and Mnemosyne internally capped at 100 and ByteRover capped at 50. Hindsight in `/snapshot` is status/config only and does not query recall/reflect.

```bash
curl http://127.0.0.1:9119/api/plugins/hermes-memory-ui/snapshot | jq
```

## Security notes

The plugin displays memory content. Treat this as private data.

Hermes dashboard plugin API routes are intended for the local dashboard. Do not expose the dashboard publicly with untrusted plugins installed. In particular, avoid binding the dashboard to `0.0.0.0` unless you understand the risk.

This plugin does not expose mutation endpoints, but it can reveal personal preferences, environment details, project facts, and other durable context stored in memory.

## Design decisions

### Why read-only first?

Memory writes are semantically loaded:

- Built-in memory has limits, delimiter parsing, locking, duplicate handling, and prompt-injection scanning.
- Holographic facts maintain FTS indexes, entity links, HRR vectors, trust scores, and memory banks.
- Mnemosyne maintains embeddings, Memoria-derived structured tables, graph rows, sleep/consolidation flows, and provider-level recall semantics.
- Built-in `memory(add)` may mirror into holographic memory, but `replace`, `remove`, and direct file edits do not reliably mirror.

A dashboard that writes directly to files or SQLite can silently corrupt memory semantics.

### Why plugin backend instead of direct browser access?

The browser cannot and should not read local files or SQLite directly. `plugin_api.py` runs inside the dashboard process, can resolve the active profile's `HERMES_HOME`, and can safely expose a narrow JSON API.

## Potential roadmap

Plugin extensions to consider (**feel free to contribute!**):

1. Safer mutation endpoints
   - built-in add/replace/remove via `tools.memory_tool.MemoryStore`
   - holographic add/update/remove via `plugins.memory.holographic.store.MemoryStore`
   - explicit warnings around mirroring and conflict semantics

2. Adapter abstraction
   - `BuiltinAdapter`
   - `HolographicAdapter`
   - `Mem0Adapter`
   - `HonchoAdapter`
   - `HindsightAdapter`
   - `MnemosyneAdapter`
   - `ByteroverAdapter`

3. Diff and hygiene tools
   - find duplicates
   - compare built-in entries mirrored to holographic facts
   - identify stale/low-trust facts
   - identify facts with no entities

4. Export
   - JSON export
   - Markdown export
   - redacted export for sharing/debugging

5. Better search
   - FTS5 query mode for holographic facts
   - entity filter
   - tag filter
   - date ranges

6. Optional dashboard slots
   - small memory usage widget in `config:top`
   - warning badge when built-in memory is near char limit

## Troubleshooting

### The Memory tab does not appear

Check plugin discovery:

```bash
curl http://127.0.0.1:9119/api/dashboard/plugins | jq
```

Force rescan:

```bash
curl http://127.0.0.1:9119/api/dashboard/plugins/rescan
```

Verify the file exists:

```bash
test -f ~/.hermes/plugins/hermes-memory-ui/dashboard/manifest.json && echo ok
```

### Backend endpoint returns 404

Plugin backend routes are mounted at dashboard startup. Restart `hermes dashboard`.

### Holographic section says DB missing

Check whether the DB exists:

```bash
test -f ~/.hermes/memory_store.db && echo exists
```

If you configured a custom path, inspect:

```bash
hermes config
```

Look for:

```yaml
plugins:
  hermes-memory-store:
    db_path: ...
```

### Browser console says SDK is undefined

The plugin script is loading before or outside the Hermes dashboard plugin runtime, or the dashboard crashed earlier. Refresh the dashboard and inspect browser devtools console/network.

## Current limitations

- Read-only only.
- Holographic search uses simple SQL `LIKE`, not FTS5 query syntax yet.
- Mem0 API mode depends on the `mem0ai` package being installed in the dashboard environment and a configured Mem0 API key.
- Local `mem0.Memory` stores are not supported; this plugin mirrors Hermes' current cloud/API-oriented Mem0 provider.
- Honcho support depends on Hermes' bundled Honcho provider helpers and a configured Honcho API key or base URL.
- Hindsight support depends on Hermes' bundled Hindsight provider helpers and a configured Hindsight Cloud/local setup.
- ByteRover support depends on the `brv` CLI being available in the dashboard environment and, for project-specific status/search, a configured or auto-detected ByteRover project.
- No pagination yet; use `limit` filter.

## License

MIT License. See [LICENSE](LICENSE).
