/* Hermes Memory UI dashboard plugin — plain IIFE, no build step required. */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const hooks = SDK.hooks;
  const components = SDK.components;
  const Card = components.Card;
  const CardHeader = components.CardHeader;
  const CardTitle = components.CardTitle;
  const CardContent = components.CardContent;
  const Badge = components.Badge;
  const Button = components.Button;
  const Input = components.Input;
  const Separator = components.Separator;
  const useState = hooks.useState;
  const useEffect = hooks.useEffect;
  const useMemo = hooks.useMemo;
  const e = React.createElement;

  function fmtTime(value) {
    if (!value) return "—";
    const date = typeof value === "number"
      ? new Date(value < 1000000000000 ? value * 1000 : value)
      : new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
  }

  function pct(value) {
    if (value === null || value === undefined) return "—";
    return String(value) + "%";
  }

  function clampPct(value) {
    const n = Number(value || 0);
    return Math.max(0, Math.min(100, n));
  }

  function classNames() {
    return Array.prototype.slice.call(arguments).filter(Boolean).join(" ");
  }

  function StatCard(props) {
    return e(Card, { className: "h-full" },
      e(CardContent, { className: "memory-ui-stat" },
        e("div", { className: "memory-ui-stat-label" }, props.label),
        e("div", { className: "memory-ui-stat-value" }, props.value),
        props.hint ? e("div", { className: "memory-ui-stat-hint" }, props.hint) : null
      )
    );
  }

  function UsageBar(props) {
    const value = clampPct(props.value);
    const tone = value >= 95 ? "danger" : value >= 80 ? "warn" : "ok";
    return e("div", { className: "memory-ui-usage" },
      e("div", { className: "memory-ui-usage-meta" },
        e("span", null, props.label),
        e("span", null, pct(props.value))
      ),
      e("div", { className: "memory-ui-usage-track" },
        e("div", { className: "memory-ui-usage-fill memory-ui-usage-" + tone, style: { width: value + "%" } })
      )
    );
  }

  function EmptyState(props) {
    return e("div", { className: "memory-ui-empty" }, props.children || "No data available.");
  }

  function ErrorBox(props) {
    if (!props.error) return null;
    return e("div", { className: "memory-ui-error" }, props.error);
  }

  function BuiltinStoreCard(props) {
    const store = props.store;
    const [expanded, setExpanded] = useState(true);
    return e(Card, null,
      e(CardHeader, { className: "memory-ui-card-header" },
        e("div", { className: "memory-ui-title-row" },
          e(CardTitle, { className: "text-base" }, store.label),
          e("div", { className: "memory-ui-badges" },
            e(Badge, { tone: "outline" }, store.entry_count + " entries"),
            e(Badge, { tone: store.exists ? "outline" : "secondary" }, store.exists ? "file found" : "not created")
          )
        ),
        e("button", { className: "memory-ui-link-button", onClick: function () { setExpanded(!expanded); } }, expanded ? "Collapse" : "Expand")
      ),
      e(CardContent, null,
        e(ErrorBox, { error: store.error }),
        e("div", { className: "memory-ui-path" }, store.path),
        e(UsageBar, { label: store.char_count + " / " + store.char_limit + " chars", value: store.usage_percent }),
        e("div", { className: "memory-ui-muted" }, "Modified: ", fmtTime(store.modified_at)),
        expanded ? e("div", { className: "memory-ui-entry-list" },
          store.entries && store.entries.length
            ? store.entries.map(function (entry, index) {
                return e("div", { key: store.id + "-" + index, className: "memory-ui-entry" },
                  e("div", { className: "memory-ui-entry-index" }, "#" + (index + 1)),
                  e("div", { className: "memory-ui-entry-content" }, entry)
                );
              })
            : e(EmptyState, null, "This memory file has no entries yet.")
        ) : null
      )
    );
  }

  function BuiltinSection(props) {
    const builtin = props.builtin;
    if (!builtin) return null;
    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Built-in memory"),
          e("p", null, "Read-only view of MEMORY.md and USER.md from the active Hermes profile.")
        ),
        e(Badge, { tone: "outline" }, builtin.total_entries + " total entries")
      ),
      e("div", { className: "memory-ui-grid-2" },
        (builtin.stores || []).map(function (store) {
          return e(BuiltinStoreCard, { key: store.id, store: store });
        })
      )
    );
  }

  function SessionSearchResultRow(props) {
    const result = props.result || {};
    const messages = (result.messages || []).slice(0, 4);
    const title = result.title || result.session_id || "Session";
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e(Badge, { tone: "outline" }, result.source || "session"),
        result.when ? e("span", { className: "memory-ui-muted" }, result.when) : null,
        result.match_message_id ? e("span", { className: "memory-ui-muted" }, "match #", result.match_message_id) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, title),
      result.snippet ? e("div", { className: "memory-ui-tags" }, result.snippet) : null,
      messages.length ? e("div", { className: "memory-ui-entry-list" },
        messages.map(function (message) {
          return e("div", { key: "session-message-" + message.id, className: "memory-ui-entry" },
            e("div", { className: "memory-ui-entry-index" }, message.role || "msg"),
            e("div", { className: "memory-ui-entry-content" }, message.content || "")
          );
        })
      ) : null
    );
  }

  function SessionSearchSection() {
    const [query, setQuery] = useState("");
    const [source, setSource] = useState("");
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    function clearSearch() {
      setQuery("");
      setSource("");
      setData(null);
      setError(null);
    }

    function runSearch() {
      if (!query.trim()) {
        setError("Enter a session search query first.");
        return;
      }
      const p = new URLSearchParams();
      p.set("query", query.trim());
      p.set("limit", "3");
      p.set("sort", "newest");
      if (source) p.set("source", source);
      setLoading(true);
      setError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/session-search?" + p.toString())
        .then(function (payload) { setData(payload); })
        .catch(function (err) { setError(err && err.message ? err.message : String(err)); })
        .finally(function () { setLoading(false); });
    }

    const results = data && data.results ? data.results : [];
    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Session search"),
          e("p", null, "Search previous Hermes sessions without changing memory state.")
        ),
        data ? e(Badge, { tone: "outline" }, (data.count || 0) + " matches") : null
      ),
      e("div", { className: "memory-ui-controls memory-ui-session-controls" },
        e("div", { className: "memory-ui-control" },
          e("label", null, "Query"),
          e(Input, {
            value: query,
            placeholder: "search past sessions...",
            onChange: function (ev) { setQuery(ev.target.value); },
            onKeyDown: function (ev) { if (ev.key === "Enter") runSearch(); }
          })
        ),
        e("div", { className: "memory-ui-control" },
          e("label", null, "Session type"),
          e("select", {
            className: "memory-ui-select",
            value: source,
            onChange: function (ev) { setSource(ev.target.value); }
          },
            e("option", { value: "" }, "All sessions"),
            e("option", { value: "cli" }, "CLI"),
            e("option", { value: "telegram" }, "Telegram"),
            e("option", { value: "cron" }, "Cron"),
            e("option", { value: "discord" }, "Discord"),
            e("option", { value: "web" }, "Web"),
            e("option", { value: "api" }, "API")
          )
        ),
        e("div", { className: "memory-ui-provider-actions" },
          e(Button, { onClick: runSearch, className: "memory-ui-refresh", disabled: loading }, loading ? "Searching..." : "Search sessions"),
          e(Button, { onClick: clearSearch, className: "memory-ui-refresh", outlined: true, disabled: loading && !query && !data && !source }, "Clear")
        )
      ),
      e(ErrorBox, { error: error || (data && data.error) }),
      data ? e("div", { className: "memory-ui-fact-list" },
        e("div", { className: "memory-ui-muted" }, "Query: ", data.query || query, data.source ? " · type: " + data.source : "", data.message ? " · " + data.message : ""),
        results.length
          ? results.map(function (result, index) { return e(SessionSearchResultRow, { key: "session-search-" + index, result: result }); })
          : e(EmptyState, null, data.error ? "Session search is unavailable." : "No matching sessions found.")
      ) : null
    );
  }

  function TrustPill(props) {
    const score = Number(props.score || 0);
    const tone = score >= 0.75 ? "high" : score >= 0.4 ? "mid" : "low";
    return e("span", { className: "memory-ui-trust memory-ui-trust-" + tone }, score.toFixed(2));
  }

  function FactRow(props) {
    const fact = props.fact;
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + fact.fact_id),
        e(Badge, { tone: "outline" }, fact.category || "general"),
        e(TrustPill, { score: fact.trust_score }),
        e("span", { className: "memory-ui-muted" }, "retrieved ", fact.retrieval_count || 0, "x"),
        e("span", { className: "memory-ui-muted" }, "helpful ", fact.helpful_count || 0, "x")
      ),
      e("div", { className: "memory-ui-fact-content" }, fact.content),
      fact.tags ? e("div", { className: "memory-ui-tags" }, "tags: ", fact.tags) : null,
      e("div", { className: "memory-ui-muted" }, "Updated: ", fmtTime(fact.updated_at), " · Created: ", fmtTime(fact.created_at))
    );
  }

  function HolographicSection(props) {
    const data = props.holographic;
    const filters = props.filters;
    const setFilters = props.setFilters;
    const refresh = props.refresh;
    if (!data) return null;

    const categories = data.categories || [];

    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Holographic memory"),
          e("p", null, "Read-only view of the local SQLite fact store used by the holographic provider.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.exists ? "outline" : "secondary" }, data.exists ? "db found" : "db missing"),
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active")
        )
      ),
      e("div", { className: "memory-ui-grid-4" },
        e(StatCard, { label: "Total facts", value: data.total_facts || 0, hint: "all rows in facts" }),
        e(StatCard, { label: "Shown", value: data.fact_count || 0, hint: "after filters" }),
        e(StatCard, { label: "Entities", value: data.entities_count || 0, hint: "entity index" }),
        e(StatCard, { label: "Banks", value: data.memory_banks_count || 0, hint: "HRR memory banks" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Search"),
            e(Input, {
              value: filters.search,
              placeholder: "content or tags...",
              onChange: function (ev) { setFilters(Object.assign({}, filters, { search: ev.target.value })); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Category"),
            e("select", {
              className: "memory-ui-select",
              value: filters.category,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { category: ev.target.value })); }
            },
              e("option", { value: "" }, "All categories"),
              categories.map(function (c) {
                return e("option", { key: c.category, value: c.category }, c.category + " (" + c.count + ")");
              })
            )
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Min trust"),
            e("select", {
              className: "memory-ui-select",
              value: filters.minTrust,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { minTrust: ev.target.value })); }
            },
              e("option", { value: "0" }, "0.0"),
              e("option", { value: "0.3" }, "0.3"),
              e("option", { value: "0.5" }, "0.5"),
              e("option", { value: "0.75" }, "0.75")
            )
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: filters.limit,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { limit: ev.target.value })); }
            },
              e("option", { value: "100" }, "100"),
              e("option", { value: "500" }, "500"),
              e("option", { value: "1000" }, "1000"),
              e("option", { value: "2000" }, "2000")
            )
          ),
          e(Button, { onClick: refresh, className: "memory-ui-refresh" }, "Apply / refresh")
        )
      ),
      e(ErrorBox, { error: data.error }),
      e("div", { className: "memory-ui-path" }, data.db_path),
      e("div", { className: "memory-ui-fact-list" },
        data.facts && data.facts.length
          ? data.facts.map(function (fact) { return e(FactRow, { key: fact.fact_id, fact: fact }); })
          : e(EmptyState, null, data.exists ? "No facts match the current filters." : "Holographic database does not exist yet.")
      )
    );
  }

  function Mem0Row(props) {
    const memory = props.memory;
    const metadata = memory.metadata && Object.keys(memory.metadata).length ? JSON.stringify(memory.metadata) : "";
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + memory.id),
        memory.score !== null && memory.score !== undefined ? e(Badge, { tone: "outline" }, "score " + Number(memory.score).toFixed(3)) : null,
        memory.user_id ? e(Badge, { tone: "outline" }, "user " + memory.user_id) : null,
        memory.agent_id ? e(Badge, { tone: "outline" }, "agent " + memory.agent_id) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, memory.memory || ""),
      metadata ? e("div", { className: "memory-ui-tags" }, "metadata: ", metadata) : null,
      e("div", { className: "memory-ui-muted" }, "Updated: ", fmtTime(memory.updated_at), " · Created: ", fmtTime(memory.created_at))
    );
  }

  function Mem0Section(props) {
    const data = props.mem0;
    const filters = props.filters;
    const setFilters = props.setFilters;
    const refresh = props.refresh;
    if (!data) return null;

    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Mem0 memory"),
          e("p", null, "Read-only view of Mem0 Platform memories scoped by the configured user_id.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active"),
          e(Badge, { tone: "outline" }, "api mode"),
          e(Badge, { tone: data.api_key_present ? "outline" : "secondary" }, data.api_key_present ? "api key present" : "no api key")
        )
      ),
      e("div", { className: "memory-ui-grid-4" },
        e(StatCard, { label: "Total memories", value: data.total_memories || 0, hint: "returned by Mem0" }),
        e(StatCard, { label: "Shown", value: data.memory_count || 0, hint: "after filters" }),
        e(StatCard, { label: "User ID", value: data.user_id || "—", hint: "read filter" }),
        e(StatCard, { label: "Agent ID", value: data.agent_id || "—", hint: "write attribution only" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-controls-compact" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Search"),
            e(Input, {
              value: filters.search,
              placeholder: "semantic search in Mem0...",
              onChange: function (ev) { setFilters(Object.assign({}, filters, { search: ev.target.value })); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: filters.limit,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { limit: ev.target.value })); }
            },
              e("option", { value: "100" }, "100"),
              e("option", { value: "500" }, "500"),
              e("option", { value: "1000" }, "1000"),
              e("option", { value: "2000" }, "2000")
            )
          ),
          e(Button, { onClick: refresh, className: "memory-ui-refresh" }, "Apply / refresh")
        )
      ),
      e(ErrorBox, { error: data.error }),
      e("div", { className: "memory-ui-path" }, data.config_path),
      e("div", { className: "memory-ui-fact-list" },
        data.memories && data.memories.length
          ? data.memories.map(function (memory) { return e(Mem0Row, { key: memory.id, memory: memory }); })
          : e(EmptyState, null, data.error ? "Mem0 memories are unavailable." : "No Mem0 memories match the current filters.")
      )
    );
  }


  function HonchoConclusionRow(props) {
    const conclusion = props.conclusion;
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + conclusion.id),
        conclusion.session_id ? e(Badge, { tone: "outline" }, "session " + conclusion.session_id) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, conclusion.content || ""),
      e("div", { className: "memory-ui-muted" }, "Updated: ", fmtTime(conclusion.updated_at), " · Created: ", fmtTime(conclusion.created_at))
    );
  }

  function HonchoSearchResultRow(props) {
    const result = props.result;
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e(Badge, { tone: "outline" }, result.source || "match"),
        result.peer_id ? e(Badge, { tone: "outline" }, "peer " + result.peer_id) : null,
        result.id ? e("span", { className: "memory-ui-muted" }, "#" + result.id) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, result.content || "")
    );
  }

  function HonchoPeerCard(props) {
    const title = props.title;
    const peer = props.peer || {};
    const card = peer.card || [];
    const conclusions = peer.conclusions || [];
    return e(Card, null,
      e(CardHeader, { className: "memory-ui-card-header" },
        e("div", null,
          e(CardTitle, { className: "text-base" }, title),
          e("div", { className: "memory-ui-muted" }, peer.peer_id || "—")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: "outline" }, ((peer.total_card_facts != null ? peer.total_card_facts : card.length)) + " card facts"),
          e(Badge, { tone: "outline" }, ((peer.total_conclusions != null ? peer.total_conclusions : conclusions.length)) + " conclusions" + (peer.total_conclusions != null && peer.total_conclusions > conclusions.length ? " (showing " + conclusions.length + " latest)" : ""))
        )
      ),
      e(CardContent, null,
        e("div", { className: "memory-ui-muted" }, "Peer card"),
        card.length
          ? e("div", { className: "memory-ui-entry-list" }, card.map(function (item, index) {
              return e("div", { key: title + "-card-" + index, className: "memory-ui-entry" },
                e("div", { className: "memory-ui-entry-index" }, "#" + (index + 1)),
                e("div", { className: "memory-ui-entry-content" }, item)
              );
            }))
          : e(EmptyState, null, "No peer card entries returned."),
        e("div", { className: "memory-ui-muted", style: { marginTop: "0.85rem" } }, "Representation"),
        peer.representation
          ? e("div", { className: "memory-ui-fact-content memory-ui-path" }, peer.representation)
          : e(EmptyState, null, "No representation returned."),
        e("div", { className: "memory-ui-muted", style: { marginTop: "0.85rem" } }, "Conclusions"),
        conclusions.length
          ? e("div", { className: "memory-ui-fact-list" }, conclusions.map(function (conclusion) {
              return e(HonchoConclusionRow, { key: conclusion.id, conclusion: conclusion });
            }))
          : e(EmptyState, null, "No conclusions returned.")
      )
    );
  }

  function HonchoSection(props) {
    const data = props.honcho;
    const filters = props.filters;
    const setFilters = props.setFilters;
    const refresh = props.refresh;
    const loading = !!props.loading;
    if (!data) return null;
    const searchResults = data.search_results || [];

    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Honcho memory"),
          e("p", null, "Read-only view of Honcho workspace, peers, cards, representations, conclusions, and context search.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active"),
          e(Badge, { tone: data.api_key_present ? "outline" : "secondary" }, data.api_key_present ? "api key present" : "no api key"),
          e(Badge, { tone: data.base_url_present ? "outline" : "secondary" }, data.base_url_present ? "base URL" : "cloud/default"),
          e(Badge, { tone: "outline" }, data.recall_mode || "hybrid")
        )
      ),
      e("div", { className: "memory-ui-grid-4" },
        e(StatCard, { label: "Workspace", value: data.workspace || "—", hint: "Honcho workspace" }),
        e(StatCard, { label: "Host", value: data.host || "—", hint: "Hermes host key" }),
        e(StatCard, { label: "User peer", value: data.user_peer || "—", hint: "target peer" }),
        e(StatCard, { label: "AI peer", value: data.ai_peer || "—", hint: "observer / assistant" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-controls-compact" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Search context"),
            e(Input, {
              value: filters.search,
              placeholder: "search Honcho context...",
              onChange: function (ev) { setFilters(Object.assign({}, filters, { search: ev.target.value })); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: filters.limit,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { limit: ev.target.value })); }
            },
              e("option", { value: "10" }, "10"),
              e("option", { value: "25" }, "25"),
              e("option", { value: "50" }, "50"),
              e("option", { value: "100" }, "100")
            )
          ),
          e(Button, { onClick: refresh, className: "memory-ui-refresh", disabled: loading }, loading ? "Refreshing..." : "Apply / refresh")
        )
      ),
      data.search ? e(Card, null,
        e(CardContent, null,
          e("div", { className: "memory-ui-title-row" },
            e("div", null,
              e("div", { className: "memory-ui-muted" }, "Applied Honcho search"),
              e("div", { className: "memory-ui-fact-content" }, data.search)
            ),
            e(Badge, { tone: "outline" }, (data.search_result_count || 0) + " text matches")
          ),
          searchResults.length
            ? e("div", { className: "memory-ui-fact-list" }, searchResults.map(function (result, index) {
                return e(HonchoSearchResultRow, { key: "honcho-search-" + index, result: result });
              }))
            : e(EmptyState, null, "No visible text matches in returned cards, representations, or conclusions. Honcho may still have used the query for context ranking.")
        )
      ) : null,
      e(ErrorBox, { error: data.error }),
      e("div", { className: "memory-ui-path" }, data.config_path),
      e("div", { className: "memory-ui-grid-2" },
        e(HonchoPeerCard, { title: "User peer", peer: data.user }),
        e(HonchoPeerCard, { title: "AI peer", peer: data.ai })
      )
    );
  }


  function ByteRoverResultRow(props) {
    const result = props.result;
    const metadata = result.metadata && Object.keys(result.metadata).length ? JSON.stringify(result.metadata) : "";
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + result.id),
        result.score !== null && result.score !== undefined ? e(Badge, { tone: "outline" }, "score " + Number(result.score).toFixed(3)) : null,
        result.path ? e(Badge, { tone: "outline" }, result.path) : null
      ),
      result.title ? e("div", { className: "memory-ui-muted" }, result.title) : null,
      e("div", { className: "memory-ui-fact-content" }, result.excerpt || ""),
      result.raw_excerpt ? e("details", { className: "memory-ui-path" },
        e("summary", null, "Full search excerpt"),
        e("div", { className: "memory-ui-fact-content memory-ui-path" }, result.raw_excerpt)
      ) : null,
      metadata && metadata !== "{}" ? e("div", { className: "memory-ui-tags" }, "metadata: ", metadata) : null
    );
  }

  function ByteRoverSection(props) {
    const data = props.byterover;
    const filters = props.filters;
    const setFilters = props.setFilters;
    const refresh = props.refresh;
    const loading = !!props.loading;
    const [query, setQuery] = useState("");
    const [queryData, setQueryData] = useState(null);
    const [queryLoading, setQueryLoading] = useState(false);
    const [queryError, setQueryError] = useState(null);
    if (!data) return null;

    function runQuery() {
      if (!query.trim()) {
        setQueryError("Enter a question first.");
        return;
      }
      const p = new URLSearchParams();
      p.set("query", query);
      setQueryLoading(true);
      setQueryError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/byterover/query?" + p.toString())
        .then(function (payload) { setQueryData(payload); })
        .catch(function (err) { setQueryError(err && err.message ? err.message : String(err)); })
        .finally(function () { setQueryLoading(false); });
    }

    const results = data.results || [];
    const status = data.status || {};
    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "ByteRover memory"),
          e("p", null, "Read-only ByteRover memory search and explicit query results via brv CLI.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active"),
          e(Badge, { tone: data.brv_available ? "outline" : "secondary" }, data.brv_available ? "brv found" : "brv missing"),
          e(Badge, { tone: data.project_exists ? "outline" : "secondary" }, data.project_exists ? "project set" : "auto project")
        )
      ),
      e("div", { className: "memory-ui-grid-1" },
        e(StatCard, { label: "Project", value: data.project_root || "auto", hint: data.project_root ? "configured project root" : "auto-detected project root" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-controls-compact" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Search"),
            e(Input, {
              value: filters.search,
              placeholder: "BM25 search in ByteRover context tree...",
              onChange: function (ev) { setFilters(Object.assign({}, filters, { search: ev.target.value })); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: filters.limit,
              onChange: function (ev) { setFilters(Object.assign({}, filters, { limit: ev.target.value })); }
            },
              e("option", { value: "10" }, "10"),
              e("option", { value: "25" }, "25"),
              e("option", { value: "50" }, "50")
            )
          ),
          e(Button, { onClick: refresh, className: "memory-ui-refresh", disabled: loading }, loading ? "Refreshing..." : "Search / refresh")
        )
      ),
      data.search ? e("div", { className: "memory-ui-fact-list" },
        e("div", { className: "memory-ui-muted" }, "Search: ", data.search, " · total found: ", data.total_found || 0),
        results.length
          ? results.map(function (result, index) { return e(ByteRoverResultRow, { key: "byterover-" + index, result: result }); })
          : e(EmptyState, null, data.error ? "ByteRover search is unavailable." : "No ByteRover results returned.")
      ) : e(EmptyState, null, "Enter a search term and click Search / refresh to query ByteRover's context tree."),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-controls-compact" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Query"),
            e(Input, {
              value: query,
              placeholder: "ask ByteRover to synthesize an answer...",
              onChange: function (ev) { setQuery(ev.target.value); }
            })
          ),
          e(Button, { onClick: runQuery, className: "memory-ui-refresh", disabled: queryLoading }, queryLoading ? "Running..." : "Run query")
        )
      ),
      e(ErrorBox, { error: data.error || queryError || (queryData && queryData.error) }),
      queryData ? e(Card, null,
        e(CardContent, null,
          e("div", { className: "memory-ui-muted" }, "ByteRover query", queryData.task_id ? " · " + queryData.task_id : ""),
          queryData.answer_summary
            ? e("div", { className: "memory-ui-fact-content" }, queryData.answer_summary)
            : (queryData.answer ? e("div", { className: "memory-ui-fact-content memory-ui-path" }, queryData.answer) : e(EmptyState, null, "No query answer returned.")),
          queryData.answer && queryData.answer_summary && queryData.answer !== queryData.answer_summary ? e("details", { className: "memory-ui-path" },
            e("summary", null, "Raw ByteRover output"),
            e("div", { className: "memory-ui-fact-content memory-ui-path" }, queryData.answer)
          ) : null,
          queryData.matched_docs && queryData.matched_docs.length ? e("div", { className: "memory-ui-tags" }, "matched docs: ", JSON.stringify(queryData.matched_docs)) : null
        )
      ) : null
    );
  }


  function HindsightResultRow(props) {
    const result = props.result;
    const metadata = result.metadata && Object.keys(result.metadata).length ? JSON.stringify(result.metadata) : "";
    const typeLabel = result.display_type || result.type;
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + result.id),
        result.score !== null && result.score !== undefined ? e(Badge, { tone: "outline" }, "score " + Number(result.score).toFixed(3)) : null,
        typeLabel ? e(Badge, { tone: "outline" }, String(typeLabel).toUpperCase()) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, result.text || ""),
      metadata ? e("div", { className: "memory-ui-tags" }, "metadata: ", metadata) : null
    );
  }

  function HindsightSection(props) {
    const data = props.hindsight;
    const [query, setQuery] = useState("");
    const [limit, setLimit] = useState("25");
    const [operationData, setOperationData] = useState(null);
    const [contentsData, setContentsData] = useState(null);
    const [operationLoading, setOperationLoading] = useState(false);
    const [contentsLoading, setContentsLoading] = useState(false);
    const [operationError, setOperationError] = useState(null);
    const [contentsError, setContentsError] = useState(null);
    if (!data) return null;

    function runOperation(kind) {
      if (!query.trim()) {
        setOperationError("Enter a query first.");
        return;
      }
      const p = new URLSearchParams();
      p.set("query", query);
      if (kind === "recall") p.set("limit", limit || "25");
      setOperationLoading(true);
      setOperationError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/hindsight/" + kind + "?" + p.toString())
        .then(function (payload) { setOperationData(payload); })
        .catch(function (err) { setOperationError(err && err.message ? err.message : String(err)); })
        .finally(function () { setOperationLoading(false); });
    }

    function refreshContents() {
      const p = new URLSearchParams();
      p.set("limit", limit || "25");
      if (query.trim()) p.set("search", query);
      setContentsLoading(true);
      setContentsError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/hindsight/contents?" + p.toString())
        .then(function (payload) { setContentsData(payload); })
        .catch(function (err) { setContentsError(err && err.message ? err.message : String(err)); })
        .finally(function () { setContentsLoading(false); });
    }

    useEffect(function () { refreshContents(); }, []);

    const results = operationData && operationData.results ? operationData.results : [];
    const memoryItems = contentsData ? (contentsData.memories || []).map(function (item) { return Object.assign({}, item, { display_type: "memory" }); }) : [];
    const documentItems = contentsData ? (contentsData.documents || []).map(function (item) { return Object.assign({}, item, { display_type: "document" }); }) : [];
    const contentItems = memoryItems.concat(documentItems);
    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Hindsight memory"),
          e("p", null, "Read-only view of Hindsight config and bank contents, plus explicit recall/reflect. No retain/write calls are exposed.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active"),
          e(Badge, { tone: "outline" }, data.mode || "cloud"),
          e(Badge, { tone: data.api_key_present ? "outline" : "secondary" }, data.api_key_present ? "api key present" : "no api key"),
          e(Badge, { tone: data.llm_key_present ? "outline" : "secondary" }, data.llm_key_present ? "LLM key present" : "no LLM key")
        )
      ),
      e("div", { className: "memory-ui-grid-4" },
        e(StatCard, { label: "Bank", value: data.bank_id || "—", hint: data.bank_id_template ? "template: " + data.bank_id_template : "resolved bank" }),
        e(StatCard, { label: "Budget", value: data.recall_budget || "mid", hint: "recall budget" }),
        e(StatCard, { label: "Memory mode", value: data.memory_mode || "hybrid", hint: "context/tools/hybrid" }),
        e(StatCard, { label: "Auto", value: (data.auto_recall ? "recall" : "—") + " / " + (data.auto_retain ? "retain" : "—"), hint: "provider lifecycle" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-hindsight-controls" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Query / content filter"),
            e(Input, {
              value: query,
              placeholder: "ask or filter Hindsight memory...",
              onChange: function (ev) { setQuery(ev.target.value); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: limit,
              onChange: function (ev) { setLimit(ev.target.value); }
            },
              e("option", { value: "10" }, "10"),
              e("option", { value: "25" }, "25"),
              e("option", { value: "50" }, "50"),
              e("option", { value: "100" }, "100")
            )
          ),
          e("div", { className: "memory-ui-hindsight-actions" },
            e(Button, { onClick: function () { runOperation("recall"); }, className: "memory-ui-refresh", disabled: operationLoading }, operationLoading ? "Running..." : "Recall"),
            e(Button, { onClick: function () { runOperation("reflect"); }, className: "memory-ui-refresh", disabled: operationLoading }, operationLoading ? "Running..." : "Reflect")
          )
        )
      ),
      e(ErrorBox, { error: data.error || operationError || contentsError || (operationData && operationData.error) || (contentsData && contentsData.error) }),
      operationData && operationData.operation === "reflect" ? e(Card, null,
        e(CardContent, null,
          e("div", { className: "memory-ui-muted" }, "Reflection", operationData.reflection_source ? " · " + operationData.reflection_source : ""),
          operationData.reflection ? e("div", { className: "memory-ui-fact-content memory-ui-path" }, operationData.reflection) : e(EmptyState, null, "No reflection returned.")
        )
      ) : null,
      operationData && operationData.operation === "recall" ? e("div", { className: "memory-ui-fact-list" },
        operationData.result_source ? e("div", { className: "memory-ui-muted" }, "Result source: ", operationData.result_source) : null,
        results.length
          ? results.map(function (result, index) { return e(HindsightResultRow, { key: "hindsight-" + index, result: result }); })
          : e(EmptyState, null, operationData.error ? "Hindsight recall is unavailable." : "No memories returned for this query.")
      ) : null,
      e("div", { className: "memory-ui-fact-list" },
        e("div", { className: "memory-ui-contents-toolbar" },
          e("div", { className: "memory-ui-muted" }, "Contents · memory units: ", contentsData ? (contentsData.memory_count || 0) : "—", " / ", contentsData ? (contentsData.total_memories || 0) : "—", " · documents: ", contentsData ? (contentsData.document_count || 0) : "—", " / ", contentsData ? (contentsData.total_documents || 0) : "—"),
          e(Button, { onClick: refreshContents, className: "memory-ui-refresh", disabled: contentsLoading }, contentsLoading ? "Refreshing..." : "Refresh contents")
        ),
        contentsLoading && !contentsData ? e(EmptyState, null, "Loading Hindsight contents...") : null,
        !contentsLoading && contentsData && contentItems.length
          ? contentItems.map(function (result, index) { return e(HindsightResultRow, { key: "hindsight-content-" + index, result: result }); })
          : null,
        !contentsLoading && contentsData && !contentItems.length ? e(EmptyState, null, "No Hindsight contents returned.") : null,
        !contentsLoading && !contentsData ? e(EmptyState, null, "Contents not loaded yet.") : null
      )
    );
  }

  function MnemosyneResultRow(props) {
    const result = props.result;
    const metadata = result.metadata && Object.keys(result.metadata).length ? JSON.stringify(result.metadata) : "";
    const typeLabel = result.display_type || result.type;
    return e("div", { className: "memory-ui-fact" },
      e("div", { className: "memory-ui-fact-top" },
        e("div", { className: "memory-ui-fact-id" }, "#" + result.id),
        result.score !== null && result.score !== undefined ? e(Badge, { tone: "outline" }, "score " + Number(result.score).toFixed(3)) : null,
        typeLabel ? e(Badge, { tone: "outline" }, String(typeLabel).toUpperCase()) : null,
        result.source ? e(Badge, { tone: "outline" }, String(result.source)) : null
      ),
      e("div", { className: "memory-ui-fact-content" }, result.text || ""),
      metadata ? e("div", { className: "memory-ui-tags" }, "metadata: ", metadata) : null,
      result.timestamp || result.created_at ? e("div", { className: "memory-ui-muted" }, "Time: ", fmtTime(result.timestamp || result.created_at)) : null
    );
  }

  function MnemosyneSection(props) {
    const data = props.mnemosyne;
    const [query, setQuery] = useState("");
    const [limit, setLimit] = useState("25");
    const [temporalWeight, setTemporalWeight] = useState("0.2");
    const [operationData, setOperationData] = useState(null);
    const [contentsData, setContentsData] = useState(null);
    const [operationLoading, setOperationLoading] = useState(false);
    const [contentsLoading, setContentsLoading] = useState(false);
    const [operationError, setOperationError] = useState(null);
    const [contentsError, setContentsError] = useState(null);
    if (!data) return null;

    function runOperation(kind) {
      if (!query.trim()) {
        setOperationError("Enter a query first.");
        return;
      }
      const p = new URLSearchParams();
      p.set("query", query);
      if (kind === "recall") {
        p.set("limit", limit || "25");
        p.set("temporal_weight", temporalWeight || "0.2");
      }
      setOperationLoading(true);
      setOperationError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/mnemosyne/" + kind + "?" + p.toString())
        .then(function (payload) { setOperationData(payload); })
        .catch(function (err) { setOperationError(err && err.message ? err.message : String(err)); })
        .finally(function () { setOperationLoading(false); });
    }

    function refreshContents() {
      const p = new URLSearchParams();
      p.set("limit", limit || "25");
      if (query.trim()) p.set("search", query);
      setContentsLoading(true);
      setContentsError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/mnemosyne/contents?" + p.toString())
        .then(function (payload) { setContentsData(payload); })
        .catch(function (err) { setContentsError(err && err.message ? err.message : String(err)); })
        .finally(function () { setContentsLoading(false); });
    }

    const visibleContents = contentsData || data;
    const results = operationData && operationData.results ? operationData.results : [];
    const memoryItems = (visibleContents.memories || []).map(function (item) { return Object.assign({}, item, { display_type: "memory" }); });
    const factItems = (visibleContents.facts || []).map(function (item) { return Object.assign({}, item, { display_type: "fact" }); });
    const contentItems = memoryItems.concat(factItems);
    return e("div", { className: "memory-ui-section" },
      e("div", { className: "memory-ui-section-header" },
        e("div", null,
          e("h2", null, "Mnemosyne memory"),
          e("p", null, "Read-only view of the local Mnemosyne SQLite store, plus explicit recall and injected-context preview.")
        ),
        e("div", { className: "memory-ui-badges" },
          e(Badge, { tone: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active"),
          e(Badge, { tone: data.db_exists ? "outline" : "secondary" }, data.db_exists ? "db found" : "db missing"),
          e(Badge, { tone: "outline" }, data.auto_sleep_enabled ? "sleep on" : "sleep off")
        )
      ),
      e("div", { className: "memory-ui-grid-4" },
        e(StatCard, { label: "Episodes", value: visibleContents.total_memories || 0, hint: "episodic + working rows" }),
        e(StatCard, { label: "Facts", value: visibleContents.total_facts || 0, hint: "memoria facts and graph rows" }),
        e(StatCard, { label: "Vectors", value: visibleContents.vector_rows || 0, hint: "sqlite-vec row index" }),
        e(StatCard, { label: "Prefetch chars", value: data.prefetch_content_chars || "default", hint: "auto-inject budget" })
      ),
      e(Card, null,
        e(CardContent, { className: "memory-ui-controls memory-ui-provider-controls" },
          e("div", { className: "memory-ui-control" },
            e("label", null, "Query / content filter"),
            e(Input, {
              value: query,
              placeholder: "ask or filter Mnemosyne memory...",
              onChange: function (ev) { setQuery(ev.target.value); }
            })
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Limit"),
            e("select", {
              className: "memory-ui-select",
              value: limit,
              onChange: function (ev) { setLimit(ev.target.value); }
            },
              e("option", { value: "10" }, "10"),
              e("option", { value: "25" }, "25"),
              e("option", { value: "50" }, "50"),
              e("option", { value: "100" }, "100")
            )
          ),
          e("div", { className: "memory-ui-control" },
            e("label", null, "Temporal"),
            e("select", {
              className: "memory-ui-select",
              value: temporalWeight,
              onChange: function (ev) { setTemporalWeight(ev.target.value); }
            },
              e("option", { value: "0" }, "0.0"),
              e("option", { value: "0.2" }, "0.2"),
              e("option", { value: "0.5" }, "0.5"),
              e("option", { value: "0.8" }, "0.8"),
              e("option", { value: "1" }, "1.0")
            )
          ),
          e("div", { className: "memory-ui-provider-actions" },
            e(Button, { onClick: function () { runOperation("recall"); }, className: "memory-ui-refresh", disabled: operationLoading }, operationLoading ? "Running..." : "Recall"),
            e(Button, { onClick: function () { runOperation("prefetch"); }, className: "memory-ui-refresh", disabled: operationLoading }, operationLoading ? "Running..." : "Preview inject")
          )
        )
      ),
      e(ErrorBox, { error: data.error || operationError || contentsError || (operationData && operationData.error) || (contentsData && contentsData.error) }),
      e("div", { className: "memory-ui-path" }, visibleContents.db_path || data.db_path),
      operationData && operationData.operation === "prefetch" ? e(Card, null,
        e(CardContent, null,
          e("div", { className: "memory-ui-muted" }, "Injected context preview · ", operationData.context_char_count || 0, " chars"),
          operationData.context ? e("div", { className: "memory-ui-fact-content memory-ui-path" }, operationData.context) : e(EmptyState, null, "No context returned.")
        )
      ) : null,
      operationData && operationData.operation === "recall" ? e("div", { className: "memory-ui-fact-list" },
        operationData.result_source ? e("div", { className: "memory-ui-muted" }, "Result source: ", operationData.result_source) : null,
        results.length
          ? results.map(function (result, index) { return e(MnemosyneResultRow, { key: "mnemosyne-result-" + index, result: result }); })
          : e(EmptyState, null, operationData.error ? "Mnemosyne recall is unavailable." : "No memories returned for this query.")
      ) : null,
      e("div", { className: "memory-ui-fact-list" },
        e("div", { className: "memory-ui-contents-toolbar" },
          e("div", { className: "memory-ui-muted" }, "Contents · memories: ", visibleContents.memory_count || 0, " / ", visibleContents.total_memories || 0, " · facts: ", visibleContents.fact_count || 0, " / ", visibleContents.total_facts || 0),
          e(Button, { onClick: refreshContents, className: "memory-ui-refresh", disabled: contentsLoading }, contentsLoading ? "Refreshing..." : "Refresh contents")
        ),
        contentsLoading && !contentsData ? e(EmptyState, null, "Loading Mnemosyne contents...") : null,
        !contentsLoading && contentItems.length
          ? contentItems.map(function (result, index) { return e(MnemosyneResultRow, { key: "mnemosyne-content-" + index, result: result }); })
          : null,
        !contentsLoading && !contentItems.length ? e(EmptyState, null, data.db_exists ? "No Mnemosyne contents returned." : "Mnemosyne database does not exist yet.") : null
      )
    );
  }

  function MemoryPage() {
    const [snapshot, setSnapshot] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [filters, setFilters] = useState({ search: "", category: "", minTrust: "0", limit: "500" });

    const query = useMemo(function () {
      const p = new URLSearchParams();
      p.set("limit", filters.limit || "500");
      p.set("min_trust", filters.minTrust || "0");
      if (filters.category) p.set("category", filters.category);
      if (filters.search) p.set("search", filters.search);
      return p.toString();
    }, [filters.search, filters.category, filters.minTrust, filters.limit]);

    function refresh() {
      setLoading(true);
      setError(null);
      SDK.fetchJSON("/api/plugins/hermes-memory-ui/snapshot?" + query)
        .then(function (data) { setSnapshot(data); })
        .catch(function (err) { setError(err && err.message ? err.message : String(err)); })
        .finally(function () { setLoading(false); });
    }

    useEffect(function () { refresh(); }, []);

    const builtin = snapshot && snapshot.builtin;
    const holographic = snapshot && snapshot.holographic;
    const mem0 = snapshot && snapshot.mem0;
    const honcho = snapshot && snapshot.honcho;
    const mnemosyne = snapshot && snapshot.mnemosyne;
    const hindsight = snapshot && snapshot.hindsight;
    const byterover = snapshot && snapshot.byterover;
    const showHolographic = !!(holographic && holographic.provider_configured);
    const showMem0 = !!(mem0 && mem0.provider_configured);
    const showHoncho = !!(honcho && honcho.provider_configured);
    const showMnemosyne = !!(mnemosyne && mnemosyne.provider_configured);
    const showHindsight = !!(hindsight && hindsight.provider_configured);
    const showByteRover = !!(byterover && byterover.provider_configured);
    const heroGridClass = showHolographic || showMem0 || showHoncho || showMnemosyne || showHindsight || showByteRover ? "memory-ui-grid-4" : "memory-ui-grid-2";

    return e("div", { className: "memory-ui-page" },
      e(Card, { className: "memory-ui-hero" },
        e(CardHeader, null,
          e("div", { className: "memory-ui-title-row" },
            e("div", null,
              e(CardTitle, { className: "text-xl" }, "Hermes Memory UI"),
              e("p", { className: "memory-ui-muted" }, "Dashboard for Hermes built-in memory and active external memory providers.")
            ),
            e("div", { className: "memory-ui-badges" },
              loading ? e(Badge, { tone: "secondary" }, "loading...") : null
            )
          )
        ),
        e(CardContent, null,
          e(ErrorBox, { error: error }),
          snapshot ? e("div", { className: heroGridClass },
            e(StatCard, { label: "Built-in entries", value: builtin ? builtin.total_entries : 0, hint: "MEMORY.md + USER.md" }),
            showHolographic ? e(StatCard, { label: "Facts", value: holographic ? holographic.total_facts : 0, hint: "holographic facts" }) : null,
            showMem0 ? e(StatCard, { label: "Mem0", value: mem0 ? mem0.total_memories : 0, hint: "Mem0 memories" }) : null,
            showHoncho ? e(StatCard, { label: "Honcho", value: honcho ? (((honcho.user.total_conclusions != null ? honcho.user.total_conclusions : (honcho.user.conclusions || []).length)) + ((honcho.ai.total_conclusions != null ? honcho.ai.total_conclusions : (honcho.ai.conclusions || []).length))) : 0, hint: "total conclusions" }) : null,
            showMnemosyne ? e(StatCard, { label: "Mnemosyne", value: mnemosyne ? (mnemosyne.total_memories || 0) : 0, hint: "local episodes" }) : null,
            showByteRover ? e(StatCard, { label: "ByteRover", value: byterover && byterover.project_exists ? "active" : "configured", hint: "search/query memory" }) : null,
            showHindsight ? e(StatCard, { label: "Hindsight", value: hindsight ? (hindsight.bank_id || "active") : "—", hint: "query-only memory" }) : null,
            e(StatCard, { label: "Hermes home", value: builtin ? "active" : "—", hint: builtin ? builtin.hermes_home : "loading" }),
            e(StatCard, { label: "Generated", value: snapshot.generated_at ? fmtTime(snapshot.generated_at) : "—", hint: "snapshot time" })
          ) : e(EmptyState, null, "Loading memory snapshot...")
        )
      ),
      snapshot ? e(React.Fragment, null,
        e(BuiltinSection, { builtin: builtin }),
        e(Separator, null),
        e(SessionSearchSection, null),
        showHolographic ? e(React.Fragment, null,
          e(Separator, null),
          e(HolographicSection, { holographic: holographic, filters: filters, setFilters: setFilters, refresh: refresh })
        ) : null,
        showMem0 ? e(React.Fragment, null,
          e(Separator, null),
          e(Mem0Section, { mem0: mem0, filters: filters, setFilters: setFilters, refresh: refresh })
        ) : null,
        showHoncho ? e(React.Fragment, null,
          e(Separator, null),
          e(HonchoSection, { honcho: honcho, filters: filters, setFilters: setFilters, refresh: refresh, loading: loading })
        ) : null,
        showMnemosyne ? e(React.Fragment, null,
          e(Separator, null),
          e(MnemosyneSection, { mnemosyne: mnemosyne })
        ) : null,
        showByteRover ? e(React.Fragment, null,
          e(Separator, null),
          e(ByteRoverSection, { byterover: byterover, filters: filters, setFilters: setFilters, refresh: refresh, loading: loading })
        ) : null,
        showHindsight ? e(React.Fragment, null,
          e(Separator, null),
          e(HindsightSection, { hindsight: hindsight })
        ) : null
      ) : null
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-memory-ui", MemoryPage);
})();
