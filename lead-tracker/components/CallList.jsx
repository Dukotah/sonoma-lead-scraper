"use client";

// Today's Call List — the daily workflow. Opens straight into the warmest
// *callable* leads (no/weak/DIY/broken site + a phone), one dial-optimized card
// at a time: tap-to-call, the problem stated plainly, the pitch ready to read,
// and one-tap outcome logging. Set a daily target and work the list down.

import { useCallback, useEffect, useMemo, useState } from "react";

const todayStr = () => new Date().toISOString().slice(0, 10);

// The provable reason to call, derived from tier + live audit.
function problem(r) {
  if (r.audit_grade === "broken") return { label: "Site is broken", cls: "p-broken" };
  if (r.audit_grade === "weak") return { label: "Weak site (no HTTPS / not mobile / slow)", cls: "p-weak" };
  if (r.tier === "A") return { label: "No real website", cls: "p-none" };
  if (r.tier === "B") return { label: `DIY site${r.builder ? ` (${r.builder})` : ""}`, cls: "p-diy" };
  return { label: "Worth a look", cls: "p-diy" };
}

export default function CallList() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState({ cities: [], categories: [] });
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");
  const [target, setTarget] = useState(20);
  const [loading, setLoading] = useState(false);
  const [hideDone, setHideDone] = useState(true);

  useEffect(() => {
    fetch("/api/facets").then((r) => r.json()).then(setFacets).catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const sp = new URLSearchParams({
      callList: "1", sort: "score", order: "desc", pageSize: "100",
    });
    if (city) sp.set("city", city);
    if (category) sp.set("category", category);
    fetch(`/api/leads?${sp}`)
      .then((r) => r.json())
      .then((d) => { setRows(d.rows || []); setTotal(d.total || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [city, category]);

  useEffect(() => { load(); }, [load]);

  async function patchLead(id, patch) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
    try {
      await fetch(`/api/leads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
    } catch (e) { console.error(e); }
  }

  // Log an outcome in one tap: sets status + stamps today as last contacted.
  const logOutcome = (id, status) =>
    patchLead(id, { status, last_contacted: todayStr() });

  const today = todayStr();
  const doneToday = useMemo(
    () => rows.filter((r) => r.last_contacted === today).length,
    [rows, today]
  );
  const visible = hideDone ? rows.filter((r) => r.last_contacted !== today) : rows;
  const pct = Math.min(100, Math.round((doneToday / Math.max(1, target)) * 100));

  return (
    <div className="cl">
      <header className="cl-head">
        <div className="cl-title">
          <h1>📞 Today&apos;s Call List</h1>
          <a className="cl-link" href="/leads">Full tracker →</a>
        </div>
        <p className="cl-sub">
          The warmest <b>callable</b> leads: a phone number + a provable website
          problem. {total.toLocaleString()} match your filters — work the top down.
        </p>

        <div className="cl-controls">
          <select value={city} onChange={(e) => setCity(e.target.value)}>
            <option value="">All cities</option>
            {facets.cities.map((c) => (
              <option key={c.city} value={c.city}>{c.city} ({c.n})</option>
            ))}
          </select>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All niches</option>
            {facets.categories.map((c) => (
              <option key={c.category} value={c.category}>{c.category} ({c.n})</option>
            ))}
          </select>
          <label className="cl-target">
            Daily target&nbsp;
            <input type="number" min={1} max={200} value={target}
              onChange={(e) => setTarget(parseInt(e.target.value) || 1)} />
          </label>
          <label className="cl-toggle">
            <input type="checkbox" checked={hideDone}
              onChange={(e) => setHideDone(e.target.checked)} />
            Hide called
          </label>
        </div>

        <div className="cl-progress">
          <div className="cl-bar"><span style={{ width: `${pct}%` }} /></div>
          <div className="cl-count">
            <b>{doneToday}</b> / {target} called today
            {doneToday >= target && " 🎉 target hit!"}
          </div>
        </div>
      </header>

      {loading && <div className="cl-empty">Loading…</div>}
      {!loading && visible.length === 0 && (
        <div className="cl-empty">
          {rows.length ? "All caught up for today — nice. 🎉"
                       : "No callable leads match. Try clearing the filters."}
        </div>
      )}

      <ol className="cl-list">
        {visible.map((r, i) => (
          <CallCard key={r.id} r={r} n={i + 1} today={today}
            patchLead={patchLead} logOutcome={logOutcome} />
        ))}
      </ol>
    </div>
  );
}

function CallCard({ r, n, today, patchLead, logOutcome }) {
  const [note, setNote] = useState(r.notes || "");
  useEffect(() => { setNote(r.notes || ""); }, [r.id]); // eslint-disable-line
  const p = problem(r);
  const calledToday = r.last_contacted === today;
  const tel = (r.phone || "").replace(/[^\d+]/g, "");

  return (
    <li className={`cl-card ${calledToday ? "done" : ""} s-${r.status?.toLowerCase()}`}>
      <div className="cl-rank">{n}</div>
      <div className="cl-body">
        <div className="cl-row1">
          <span className="cl-name">{r.name}</span>
          <span className={`cl-prob ${p.cls}`}>{p.label}</span>
          {r.score != null && <span className="cl-score">score {r.score}</span>}
          {calledToday && <span className="cl-doneflag">✓ called today</span>}
        </div>
        <div className="cl-meta">
          {r.category && <span>{r.category}</span>}
          {r.city && <span>· {r.city}</span>}
          {r.address && <span className="cl-addr">· {r.address}</span>}
          {r.status && r.status !== "New" && <span className="cl-status">· {r.status}</span>}
        </div>

        {r.pitch && (
          <div className="cl-pitch">
            <p>{r.pitch}</p>
            <button className="cl-copy"
              onClick={() => navigator.clipboard?.writeText(r.pitch)}>Copy pitch</button>
          </div>
        )}

        <div className="cl-actions">
          <a className="cl-call" href={tel ? `tel:${tel}` : undefined}>
            📞 {r.phone_fmt || r.phone}
          </a>
          <span className="cl-outcomes">
            <button className="oc oc-win" onClick={() => logOutcome(r.id, "Quoted")}
              title="Reached them, pitched">Connected → Quoted</button>
            <button className="oc oc-vm" onClick={() => logOutcome(r.id, "Contacted")}
              title="Left a voicemail / will retry">Left VM</button>
            <button className="oc oc-no" onClick={() => logOutcome(r.id, "Lost")}
              title="Not interested">Not interested</button>
          </span>
        </div>

        <div className="cl-noterow">
          <input className="cl-note" value={note} placeholder="Quick note…"
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => { if (note !== (r.notes || "")) patchLead(r.id, { notes: note }); }} />
        </div>
      </div>
    </li>
  );
}
