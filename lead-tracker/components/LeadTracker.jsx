"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const STATUSES = ["New", "Contacted", "Quoted", "Won", "Lost"];
const TIER_LABEL = { A: "A · hot", B: "B · DIY site", C: "C · has site" };

// Color band for the score chip.
function scoreBand(s) {
  if (s == null) return "na";
  if (s >= 80) return "hi";
  if (s >= 55) return "mid";
  return "lo";
}

// Tooltip summarizing live-audit results, if this lead has been audited.
function auditTitle(r) {
  if (!r.audit_grade) return undefined;
  const bits = [];
  if (r.audit_status) bits.push(`HTTP ${r.audit_status}`);
  bits.push(r.audit_https ? "HTTPS" : "no HTTPS");
  bits.push(r.audit_mobile ? "mobile-friendly" : "not mobile");
  if (r.audit_load_ms != null) bits.push(`${r.audit_load_ms}ms`);
  if (r.audit_builder) bits.push(`built on ${r.audit_builder}`);
  if (r.audit_error) bits.push(r.audit_error);
  return `Live audit: ${bits.join(" · ")}`;
}

function useDebounced(value, ms) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function LeadTracker() {
  const [filters, setFilters] = useState({
    q: "", city: "", category: "", tier: "", status: "",
    hasWebsite: "", hasPhone: "", favorite: "", builder: "", minScore: "", audit: "",
  });
  const [sort, setSort] = useState({ sort: "tier", order: "asc" });
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const [data, setData] = useState({ rows: [], total: 0, pages: 0 });
  const [facets, setFacets] = useState({ cities: [], categories: [] });
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openNotes, setOpenNotes] = useState(null); // lead id with notes editor open

  const debouncedQ = useDebounced(filters.q, 300);

  // Build the query string shared by the list endpoint and the export link.
  const queryString = useMemo(() => {
    const sp = new URLSearchParams();
    const f = { ...filters, q: debouncedQ };
    for (const [k, v] of Object.entries(f)) if (v) sp.set(k, v);
    sp.set("sort", sort.sort);
    sp.set("order", sort.order);
    return sp.toString();
  }, [filters, debouncedQ, sort]);

  const refreshStats = useCallback(() => {
    fetch("/api/stats").then((r) => r.json()).then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/facets").then((r) => r.json()).then(setFacets).catch(() => {});
    refreshStats();
  }, [refreshStats]);

  // Reset to page 1 whenever filters or sort change.
  useEffect(() => { setPage(1); }, [queryString]);

  useEffect(() => {
    setLoading(true);
    const sp = new URLSearchParams(queryString);
    sp.set("page", String(page));
    sp.set("pageSize", String(pageSize));
    const ctrl = new AbortController();
    fetch(`/api/leads?${sp.toString()}`, { signal: ctrl.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((e) => { if (e.name !== "AbortError") console.error(e); })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [queryString, page]);

  function setF(k, v) { setFilters((f) => ({ ...f, [k]: v })); }

  // Optimistically patch a row, persist to the API, then refresh stats.
  async function patchLead(id, patch) {
    setData((d) => ({
      ...d,
      rows: d.rows.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }));
    try {
      await fetch(`/api/leads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      refreshStats();
    } catch (e) { console.error(e); }
  }

  const clearFilters = () =>
    setFilters({ q: "", city: "", category: "", tier: "", status: "",
      hasWebsite: "", hasPhone: "", favorite: "", builder: "", minScore: "", audit: "" });

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="lt">
      <header className="lt-head">
        <div className="lt-titlebar">
          <h1>Lead Tracker</h1>
          <a className="lt-today-link" href="/today">📞 Today&apos;s Call List →</a>
        </div>
        {stats && (
          <div className="lt-stats">
            <Stat label="Leads" value={stats.total} />
            <Stat label="Tier A (hot)" value={stats.tierA} accent />
            <Stat label="Tier B (DIY)" value={stats.tierB} />
            <Stat label="With phone" value={stats.withPhone} />
            {stats.badSites > 0 && (
              <button
                className={`lt-stat as-button ${filters.audit === "bad" ? "accent" : ""}`}
                onClick={() => setF("audit", filters.audit === "bad" ? "" : "bad")}
                title="Audited sites graded weak or broken — provable upsells"
              >
                <span className="lt-stat-n">{(stats.badSites ?? 0).toLocaleString()}</span>
                <span className="lt-stat-l">🔥 Bad sites</span>
              </button>
            )}
            <Stat label="Avg score" value={stats.avgScore} />
            <Stat label="★ Favorites" value={stats.favorites} />
            <span className="lt-pipe">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  className={`lt-chip s-${s.toLowerCase()} ${filters.status === s ? "on" : ""}`}
                  onClick={() => setF("status", filters.status === s ? "" : s)}
                  title={`Filter by ${s}`}
                >
                  {s} <b>{stats.status?.[s] ?? 0}</b>
                </button>
              ))}
            </span>
          </div>
        )}
      </header>

      <div className="lt-toolbar">
        <input
          className="lt-search"
          placeholder="Search name, category, city, address…"
          value={filters.q}
          onChange={(e) => setF("q", e.target.value)}
        />
        <select value={filters.city} onChange={(e) => setF("city", e.target.value)}>
          <option value="">All cities</option>
          {facets.cities.map((c) => (
            <option key={c.city} value={c.city}>{c.city} ({c.n})</option>
          ))}
        </select>
        <select value={filters.category} onChange={(e) => setF("category", e.target.value)}>
          <option value="">All niches</option>
          {facets.categories.map((c) => (
            <option key={c.category} value={c.category}>{c.category} ({c.n})</option>
          ))}
        </select>
        <select value={filters.tier} onChange={(e) => setF("tier", e.target.value)}>
          <option value="">Any tier</option>
          <option value="A">A · no/weak site (hot)</option>
          <option value="B">B · DIY builder (upsell)</option>
          <option value="C">C · has a website</option>
        </select>
        <select value={filters.builder} onChange={(e) => setF("builder", e.target.value)}>
          <option value="">Any builder</option>
          {(facets.builders || []).map((b) => (
            <option key={b.builder} value={b.builder}>{b.builder} ({b.n})</option>
          ))}
        </select>
        <select value={filters.minScore} onChange={(e) => setF("minScore", e.target.value)}>
          <option value="">Any score</option>
          <option value="90">Score ≥ 90</option>
          <option value="75">Score ≥ 75</option>
          <option value="50">Score ≥ 50</option>
        </select>
        <select value={filters.hasWebsite} onChange={(e) => setF("hasWebsite", e.target.value)}>
          <option value="">Website: any</option>
          <option value="no">No website</option>
          <option value="yes">Has website</option>
        </select>
        <select value={filters.audit} onChange={(e) => setF("audit", e.target.value)}
          title="Live website-audit results">
          <option value="">Audit: any</option>
          <option value="bad">🔥 Bad website (weak/broken)</option>
          <option value="broken">Broken</option>
          <option value="weak">Weak</option>
          <option value="good">Good</option>
          <option value="yes">Audited</option>
          <option value="no">Not yet audited</option>
        </select>
        <label className="lt-toggle">
          <input type="checkbox" checked={filters.hasPhone === "yes"}
            onChange={(e) => setF("hasPhone", e.target.checked ? "yes" : "")} />
          Has phone
        </label>
        <label className="lt-toggle">
          <input type="checkbox" checked={filters.favorite === "1"}
            onChange={(e) => setF("favorite", e.target.checked ? "1" : "")} />
          ★ Favorites
        </label>
        {activeFilterCount > 0 && (
          <button className="lt-clear" onClick={clearFilters}>Clear ({activeFilterCount})</button>
        )}
        <a className="lt-export" href={`/api/export?${queryString}`}>Export CSV</a>
      </div>

      <div className="lt-meta">
        {loading ? "Loading…" : `${data.total.toLocaleString()} leads`}
        {data.pages > 1 && ` · page ${page} of ${data.pages}`}
      </div>

      <table className="lt-table">
        <thead>
          <tr>
            <Th label="★" />
            <Th label="Business" col="name" sort={sort} setSort={setSort} />
            <Th label="Niche" col="category" sort={sort} setSort={setSort} />
            <Th label="City" col="city" sort={sort} setSort={setSort} />
            <Th label="Phone" />
            <Th label="Website" />
            <Th label="Tier" col="tier" sort={sort} setSort={setSort} />
            <Th label="Score" col="score" sort={sort} setSort={setSort} />
            <Th label="Status" />
            <Th label="Notes" />
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <Row key={r.id} r={r} patchLead={patchLead}
              openNotes={openNotes} setOpenNotes={setOpenNotes} />
          ))}
          {!loading && data.rows.length === 0 && (
            <tr><td colSpan={10} className="lt-empty">No leads match these filters.</td></tr>
          )}
        </tbody>
      </table>

      {data.pages > 1 && (
        <div className="lt-pager">
          <button disabled={page <= 1} onClick={() => setPage(1)}>« First</button>
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹ Prev</button>
          <span>Page {page} / {data.pages}</span>
          <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>Next ›</button>
          <button disabled={page >= data.pages} onClick={() => setPage(data.pages)}>Last »</button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className={`lt-stat ${accent ? "accent" : ""}`}>
      <span className="lt-stat-n">{(value ?? 0).toLocaleString()}</span>
      <span className="lt-stat-l">{label}</span>
    </div>
  );
}

function Th({ label, col, sort, setSort }) {
  if (!col) return <th>{label}</th>;
  const active = sort.sort === col;
  const arrow = active ? (sort.order === "asc" ? " ▲" : " ▼") : "";
  return (
    <th className="lt-sortable" onClick={() =>
      setSort((s) => s.sort === col
        ? { sort: col, order: s.order === "asc" ? "desc" : "asc" }
        : { sort: col, order: "asc" })}>
      {label}{arrow}
    </th>
  );
}

function Row({ r, patchLead, openNotes, setOpenNotes }) {
  const [draft, setDraft] = useState(r.notes || "");
  useEffect(() => { setDraft(r.notes || ""); }, [r.id, r.notes]);
  const isOpen = openNotes === r.id;
  const website = (r.website || "").trim();
  const websiteUrl = website && !/^https?:\/\//i.test(website) ? `https://${website}` : website;

  return (
    <>
      <tr className={`s-row-${r.status?.toLowerCase()}`}>
        <td className="lt-fav">
          <button title="Toggle favorite"
            className={r.favorite ? "on" : ""}
            onClick={() => patchLead(r.id, { favorite: r.favorite ? 0 : 1 })}>
            {r.favorite ? "★" : "☆"}
          </button>
        </td>
        <td className="lt-name">
          {r.name}
          {r.address && <div className="lt-addr">{r.address}</div>}
        </td>
        <td>{r.category || "—"}</td>
        <td>{r.city || "—"}</td>
        <td>{r.phone ? <a href={`tel:${r.phone}`}>{r.phone_fmt || r.phone}</a> : "—"}
          {r.best_contact && r.best_contact !== "none" && r.best_contact !== "phone" &&
            <div className="lt-best">via {r.best_contact}</div>}
        </td>
        <td className="lt-web">
          {website
            ? <a href={websiteUrl} target="_blank" rel="noreferrer">{website.replace(/^https?:\/\//, "")}</a>
            : <span className="lt-none" title={r.tier_reason}>none</span>}
        </td>
        <td><span className={`lt-tier t-${r.tier?.toLowerCase()}`} title={r.tier_reason}>
          {TIER_LABEL[r.tier] || r.tier}</span>
          {r.builder && <span className="lt-builder" title={`Built on ${r.builder}`}>{r.builder}</span>}
          {r.audit_grade && <span className={`lt-audit g-${r.audit_grade}`} title={auditTitle(r)}>{r.audit_grade}</span>}
        </td>
        <td><span className={`lt-score sc-${scoreBand(r.score)}`} title="Lead priority 0–100">{r.score ?? "—"}</span></td>
        <td>
          <select className={`lt-status s-${r.status?.toLowerCase()}`}
            value={r.status}
            onChange={(e) => patchLead(r.id, { status: e.target.value })}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </td>
        <td>
          <button className={`lt-notes-btn ${r.notes ? "has" : ""}`}
            onClick={() => setOpenNotes(isOpen ? null : r.id)}>
            {r.notes ? "📝 edit" : "+ note"}
          </button>
        </td>
      </tr>
      {isOpen && (
        <tr className="lt-notes-row">
          <td colSpan={10}>
            {r.pitch && (
              <div className="lt-pitch">
                <div className="lt-pitch-label">Suggested pitch</div>
                <p className="lt-pitch-text">{r.pitch}</p>
                <button className="lt-copy"
                  onClick={() => navigator.clipboard?.writeText(r.pitch)}>Copy</button>
              </div>
            )}
            <div className="lt-notes-edit">
              <textarea rows={3} value={draft} onChange={(e) => setDraft(e.target.value)}
                placeholder="Call notes, pitch angle, follow-up date…" />
              <div className="lt-notes-actions">
                <label>Last contacted:&nbsp;
                  <input type="date" value={r.last_contacted || ""}
                    onChange={(e) => patchLead(r.id, { last_contacted: e.target.value })} />
                </label>
                <span className="lt-spacer" />
                <button onClick={() => setOpenNotes(null)}>Cancel</button>
                <button className="primary"
                  onClick={() => { patchLead(r.id, { notes: draft }); setOpenNotes(null); }}>
                  Save note
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
