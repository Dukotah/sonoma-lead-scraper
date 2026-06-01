// Data layer for the lead tracker. Plain Node + better-sqlite3, no framework
// imports, so it can be unit-tested directly and reused from any route handler.
import Database from "better-sqlite3";
import path from "node:path";

let _db = null;

export function getDb() {
  if (_db) return _db;
  const file =
    process.env.LEADS_DB || path.join(process.cwd(), "data", "leads.sqlite");
  _db = new Database(file, { fileMustExist: true });
  _db.pragma("journal_mode = WAL");
  // The build script creates this too; create-if-missing so the app also works
  // against a freshly-shipped DB that has never been written to.
  _db.exec(`CREATE TABLE IF NOT EXISTS crm (
    lead_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'New',
    notes TEXT,
    last_contacted TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
  )`);
  // Live-audit results, written by scripts/audit_websites.py (run locally where
  // outbound HTTP is allowed). Kept in its own table so it survives data rebuilds,
  // same as crm. create-if-missing so the app works before any audit has run.
  _db.exec(`CREATE TABLE IF NOT EXISTS audit (
    lead_id TEXT PRIMARY KEY,
    http_status INTEGER,
    https INTEGER,
    mobile INTEGER,
    load_ms INTEGER,
    builder_live TEXT,
    title TEXT,
    audit_grade TEXT,
    error TEXT,
    checked_at TEXT
  )`);
  return _db;
}

export const STATUSES = ["New", "Contacted", "Quoted", "Won", "Lost"];
const SORTS = {
  tier: "l.tier",
  name: "l.name",
  city: "l.city",
  category: "l.category",
  score: "l.score",
  updated: "c.updated_at",
};

// Turn a free-text query into a safe FTS5 prefix-match expression:
//   "corner cafe" -> '"corner"* "cafe"*'  (implicit AND, prefix on each token)
function ftsExpr(q) {
  const tokens = String(q)
    .toLowerCase()
    .match(/[a-z0-9]+/g);
  if (!tokens || !tokens.length) return null;
  return tokens.map((t) => `"${t}"*`).join(" ");
}

// Shared WHERE builder for list, count, and export. Returns { where, params }.
function buildFilter(p) {
  const where = [];
  const params = {};

  const fts = p.q ? ftsExpr(p.q) : null;
  if (fts) {
    where.push("l.rowid IN (SELECT rowid FROM leads_fts WHERE leads_fts MATCH @fts)");
    params.fts = fts;
  }
  if (p.city) {
    where.push("l.city = @city");
    params.city = p.city;
  }
  if (p.category) {
    where.push("l.category = @category");
    params.category = p.category;
  }
  if (p.tier) {
    where.push("l.tier = @tier");
    params.tier = p.tier;
  }
  if (p.status) {
    where.push("COALESCE(c.status, 'New') = @status");
    params.status = p.status;
  }
  if (p.hasWebsite === "yes") where.push("l.website IS NOT NULL AND l.website <> ''");
  if (p.hasWebsite === "no") where.push("(l.website IS NULL OR l.website = '')");
  if (p.hasPhone === "yes") where.push("l.phone IS NOT NULL AND l.phone <> ''");
  if (p.hasEmail === "yes") where.push("l.email IS NOT NULL AND l.email <> ''");
  if (p.builder) {
    where.push("l.builder = @builder");
    params.builder = p.builder;
  }
  if (p.minScore) {
    const ms = parseInt(p.minScore);
    if (!Number.isNaN(ms)) {
      where.push("l.score >= @minScore");
      params.minScore = ms;
    }
  }
  if (p.favorite === "1" || p.favorite === true)
    where.push("COALESCE(c.favorite, 0) = 1");
  // Live-audit grade filter. "bad" = the money filter: a real site that's
  // weak or broken — a provable upsell. Also expose each grade + audited/not.
  if (p.audit === "bad") where.push("a.audit_grade IN ('weak','broken')");
  else if (p.audit === "broken") where.push("a.audit_grade = 'broken'");
  else if (p.audit === "weak") where.push("a.audit_grade = 'weak'");
  else if (p.audit === "good") where.push("a.audit_grade = 'good'");
  else if (p.audit === "yes") where.push("a.audit_grade IS NOT NULL");
  else if (p.audit === "no") where.push("a.audit_grade IS NULL");
  // Today's-call-list filter: the warmest *callable* leads in one shot —
  // reachable by phone AND with a provable website need (no/weak site = Tier A,
  // DIY builder = Tier B, or a live audit that came back weak/broken).
  if (p.callList === "1" || p.callList === true) {
    where.push("l.phone IS NOT NULL AND l.phone <> ''");
    where.push("(l.tier IN ('A','B') OR a.audit_grade IN ('weak','broken'))");
  }

  return { where: where.length ? `WHERE ${where.join(" AND ")}` : "", params };
}

const SELECT_COLS = `
  l.id, l.name, l.category, l.city, l.address, l.phone, l.website, l.email,
  l.socials, l.tier, l.tier_reason, l.lat, l.lon,
  l.score, l.builder, l.phone_fmt, l.area_code, l.social_platforms,
  l.email_owned, l.completeness, l.best_contact, l.pitch,
  a.http_status AS audit_status, a.https AS audit_https, a.mobile AS audit_mobile,
  a.load_ms AS audit_load_ms, a.builder_live AS audit_builder,
  a.audit_grade, a.error AS audit_error, a.checked_at AS audit_checked_at,
  COALESCE(c.status, 'New') AS status,
  c.notes, c.last_contacted,
  COALESCE(c.favorite, 0) AS favorite,
  c.updated_at`;

// Every read joins crm (tracking) + audit (live website results) onto leads.
const FROM_JOINS = `
  FROM leads l
  LEFT JOIN crm c ON c.lead_id = l.id
  LEFT JOIN audit a ON a.lead_id = l.id`;

export function queryLeads(p = {}) {
  const db = getDb();
  const { where, params } = buildFilter(p);

  const total = db
    .prepare(`SELECT COUNT(*) n ${FROM_JOINS} ${where}`)
    .get(params).n;

  const page = Math.max(1, parseInt(p.page) || 1);
  const pageSize = Math.min(200, Math.max(1, parseInt(p.pageSize) || 50));
  const sortCol = SORTS[p.sort] || "l.tier";
  const order = String(p.order).toLowerCase() === "desc" ? "DESC" : "ASC";
  // Stable, sensible secondary ordering; NULLs sort last for score/updated.
  let orderBy;
  if (p.sort === "updated") {
    orderBy = `c.updated_at IS NULL, c.updated_at ${order}`;
  } else if (p.sort === "score") {
    orderBy = `l.score IS NULL, l.score ${order}, l.name ASC`;
  } else {
    orderBy = `${sortCol} ${order}, l.name ASC`;
  }

  const rows = db
    .prepare(
      `SELECT ${SELECT_COLS} ${FROM_JOINS}
       ${where} ORDER BY ${orderBy}
       LIMIT @_limit OFFSET @_offset`
    )
    .all({ ...params, _limit: pageSize, _offset: (page - 1) * pageSize });

  return { rows, total, page, pageSize, pages: Math.ceil(total / pageSize) };
}

// All matching rows (no paging) for CSV export.
export function exportLeads(p = {}) {
  const db = getDb();
  const { where, params } = buildFilter(p);
  return db
    .prepare(
      `SELECT ${SELECT_COLS} ${FROM_JOINS}
       ${where} ORDER BY l.score IS NULL, l.score DESC, l.name ASC`
    )
    .all(params);
}

export function getFacets() {
  const db = getDb();
  const cities = db
    .prepare(
      "SELECT city, COUNT(*) n FROM leads WHERE city IS NOT NULL AND city <> '' " +
        "GROUP BY city ORDER BY n DESC LIMIT 300"
    )
    .all();
  const categories = db
    .prepare(
      "SELECT category, COUNT(*) n FROM leads WHERE category IS NOT NULL AND category <> '' " +
        "GROUP BY category ORDER BY n DESC LIMIT 300"
    )
    .all();
  const builders = db
    .prepare(
      "SELECT builder, COUNT(*) n FROM leads WHERE builder IS NOT NULL AND builder <> '' " +
        "GROUP BY builder ORDER BY n DESC"
    )
    .all();
  return { cities, categories, builders, statuses: STATUSES };
}

export function getStats() {
  const db = getDb();
  const total = db.prepare("SELECT COUNT(*) n FROM leads").get().n;
  const tierA = db.prepare("SELECT COUNT(*) n FROM leads WHERE tier = 'A'").get().n;
  const tierB = db.prepare("SELECT COUNT(*) n FROM leads WHERE tier = 'B'").get().n;
  const tierC = db.prepare("SELECT COUNT(*) n FROM leads WHERE tier = 'C'").get().n;
  const withPhone = db
    .prepare("SELECT COUNT(*) n FROM leads WHERE phone IS NOT NULL AND phone <> ''")
    .get().n;
  const avgScore = db.prepare("SELECT ROUND(AVG(score),1) v FROM leads").get().v;
  const audited = db.prepare("SELECT COUNT(*) n FROM audit").get().n;
  const badSites = db
    .prepare("SELECT COUNT(*) n FROM audit WHERE audit_grade IN ('weak','broken')")
    .get().n;
  const byStatus = db
    .prepare(
      `SELECT COALESCE(c.status, 'New') status, COUNT(*) n
       FROM leads l LEFT JOIN crm c ON c.lead_id = l.id
       GROUP BY status`
    )
    .all();
  const favorites = db.prepare("SELECT COUNT(*) n FROM crm WHERE favorite = 1").get().n;
  const status = {};
  for (const s of STATUSES) status[s] = 0;
  for (const r of byStatus) status[r.status] = r.n;
  return { total, tierA, tierB, tierC, withPhone, avgScore, audited, badSites, favorites, status };
}

// Partial update of a lead's CRM state. Only provided keys change; pass notes:""
// to clear a note. Returns the merged crm row.
export function updateCrm(id, patch = {}) {
  const db = getDb();
  const exists = db.prepare("SELECT 1 FROM leads WHERE id = ?").get(id);
  if (!exists) return null;

  const cur =
    db.prepare("SELECT * FROM crm WHERE lead_id = ?").get(id) || {
      lead_id: id,
      status: "New",
      notes: null,
      last_contacted: null,
      favorite: 0,
    };

  const next = {
    lead_id: id,
    status: patch.status !== undefined ? patch.status : cur.status,
    notes: patch.notes !== undefined ? patch.notes : cur.notes,
    last_contacted:
      patch.last_contacted !== undefined ? patch.last_contacted : cur.last_contacted,
    favorite:
      patch.favorite !== undefined ? (patch.favorite ? 1 : 0) : cur.favorite,
    updated_at: new Date().toISOString(),
  };
  if (next.status && !STATUSES.includes(next.status)) next.status = cur.status;

  db.prepare(
    `INSERT INTO crm (lead_id, status, notes, last_contacted, favorite, updated_at)
     VALUES (@lead_id, @status, @notes, @last_contacted, @favorite, @updated_at)
     ON CONFLICT(lead_id) DO UPDATE SET
       status = @status, notes = @notes, last_contacted = @last_contacted,
       favorite = @favorite, updated_at = @updated_at`
  ).run(next);
  return next;
}
