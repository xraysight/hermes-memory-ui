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
    if (typeof value === "number") {
      return new Date(value * 1000).toLocaleString();
    }
    return String(value).replace("T", " ").replace(/\.\d+$/, "");
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
            e(Badge, { variant: "outline" }, store.entry_count + " entries"),
            e(Badge, { variant: store.exists ? "outline" : "secondary" }, store.exists ? "file found" : "not created")
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
        e(Badge, { variant: "outline" }, builtin.total_entries + " total entries")
      ),
      e("div", { className: "memory-ui-grid-2" },
        (builtin.stores || []).map(function (store) {
          return e(BuiltinStoreCard, { key: store.id, store: store });
        })
      )
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
        e(Badge, { variant: "outline" }, fact.category || "general"),
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
          e(Badge, { variant: data.exists ? "outline" : "secondary" }, data.exists ? "db found" : "db missing"),
          e(Badge, { variant: data.provider_configured ? "outline" : "secondary" }, data.provider_configured ? "active provider" : "not active")
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
          e(Button, { onClick: refresh, className: "memory-ui-refresh" }, "Refresh")
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

    useEffect(function () { refresh(); }, [query]);

    const builtin = snapshot && snapshot.builtin;
    const holographic = snapshot && snapshot.holographic;
    const showHolographic = !!(holographic && holographic.provider_configured);

    return e("div", { className: "memory-ui-page" },
      e(Card, { className: "memory-ui-hero" },
        e(CardHeader, null,
          e("div", { className: "memory-ui-title-row" },
            e("div", null,
              e(CardTitle, { className: "text-xl" }, "Hermes Memory UI"),
              e("p", { className: "memory-ui-muted" }, "Dashboard for Hermes built-in memory and active external memory providers.")
            ),
            e("div", { className: "memory-ui-badges" },
              loading ? e(Badge, { variant: "secondary" }, "loading...") : null
            )
          )
        ),
        e(CardContent, null,
          e(ErrorBox, { error: error }),
          snapshot ? e("div", { className: showHolographic ? "memory-ui-grid-4" : "memory-ui-grid-2" },
            e(StatCard, { label: "Built-in entries", value: builtin ? builtin.total_entries : 0, hint: "MEMORY.md + USER.md" }),
            showHolographic ? e(StatCard, { label: "Facts", value: holographic ? holographic.total_facts : 0, hint: "holographic facts" }) : null,
            e(StatCard, { label: "Hermes home", value: builtin ? "active" : "—", hint: builtin ? builtin.hermes_home : "loading" }),
            e(StatCard, { label: "Generated", value: snapshot.generated_at ? fmtTime(snapshot.generated_at) : "—", hint: "snapshot time" })
          ) : e(EmptyState, null, "Loading memory snapshot...")
        )
      ),
      snapshot ? e(React.Fragment, null,
        e(BuiltinSection, { builtin: builtin }),
        showHolographic ? e(React.Fragment, null,
          e(Separator, null),
          e(HolographicSection, { holographic: holographic, filters: filters, setFilters: setFilters, refresh: refresh })
        ) : null
      ) : null
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-memory-ui", MemoryPage);
})();
