# Multi-Tenant Data Model — from personal tool to platform

Today the CRM is single-user: `leads` (shared facts) + `crm` (one row of
status/notes per lead) + `audit`. To let *other people* use it, the one thing
that must change is **separating shared lead facts from per-user working state.**

This sketches that model. It's deliberately incremental — you can ship it on
SQLite and migrate to Postgres later without redesigning.

---

## The core principle

```
  SHARED (one copy, everyone reads)        PER-TENANT (private working state)
  ┌─────────────────────────────┐          ┌──────────────────────────────────┐
  │ leads   (51k businesses)     │          │ lead_state (status/notes/fav)    │
  │ audit   (website grades)     │  ◄────►  │ lists + list_items (saved lists) │
  │                              │   join   │ activity (call log / timeline)   │
  └─────────────────────────────┘  on id   └──────────────────────────────────┘
```

**Never copy the 51k leads per user.** A business's name/phone/website and its
audit grade are facts — shared. What's private is *what this user did about it*:
their status, notes, favorites, saved lists, call history. Key all of that by
`(tenant_id, lead_id)`.

---

## Tables

### Shared (already exist, unchanged)
- **`leads`** — canonical business facts (see `SCHEMA.md`). Global.
- **`audit`** — live website-audit results. Global (the grade is a fact about the
  site, true for everyone).

### Identity & tenancy (new)
```sql
CREATE TABLE accounts (            -- a workspace / company (the billable unit)
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'free',   -- free | pro | agency
  created_at  TEXT NOT NULL
);

CREATE TABLE users (
  id          TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  email       TEXT NOT NULL UNIQUE,
  role        TEXT NOT NULL DEFAULT 'member',  -- owner | admin | member
  created_at  TEXT NOT NULL
);
```
*Tenant = `account_id`.* Users belong to one account; data is scoped to the
account so teammates share lists and pipeline. (If you want strict
solo-users-only at first, treat `account_id == user_id`.)

### Per-tenant working state (new — replaces today's single `crm` table)
```sql
-- One row per (account, lead) the account has touched. Sparse: only created
-- when someone first acts on a lead, so it stays small vs. the 51k catalog.
CREATE TABLE lead_state (
  account_id     TEXT NOT NULL REFERENCES accounts(id),
  lead_id        TEXT NOT NULL REFERENCES leads(id),
  status         TEXT NOT NULL DEFAULT 'New',   -- New|Contacted|Quoted|Won|Lost
  favorite       INTEGER NOT NULL DEFAULT 0,
  notes          TEXT,
  last_contacted TEXT,
  owner_user_id  TEXT REFERENCES users(id),     -- assigned rep
  updated_at     TEXT NOT NULL,
  PRIMARY KEY (account_id, lead_id)
);

-- Saved lists / segments ("Santa Rosa salons, no website").
CREATE TABLE lists (
  id          TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  name        TEXT NOT NULL,
  -- Optional: store the filter that defined it, so it can be "smart"/re-runnable.
  filter_json TEXT,
  created_by  TEXT REFERENCES users(id),
  created_at  TEXT NOT NULL
);

CREATE TABLE list_items (
  list_id   TEXT NOT NULL REFERENCES lists(id),
  lead_id   TEXT NOT NULL REFERENCES leads(id),
  added_at  TEXT NOT NULL,
  PRIMARY KEY (list_id, lead_id)
);

-- Append-only activity timeline (calls, emails, status changes, notes).
CREATE TABLE activity (
  id          TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL REFERENCES accounts(id),
  lead_id     TEXT NOT NULL REFERENCES leads(id),
  user_id     TEXT REFERENCES users(id),
  kind        TEXT NOT NULL,        -- call | email | note | status_change | sms
  body        TEXT,
  created_at  TEXT NOT NULL
);
```

### Indexes that matter
```sql
CREATE INDEX idx_lead_state_acct   ON lead_state(account_id, status);
CREATE INDEX idx_list_items_lead   ON list_items(lead_id);
CREATE INDEX idx_activity_lead     ON activity(account_id, lead_id, created_at);
```

---

## How reads change

Every lead query gets the tenant's state joined in by account. The current
single-user query:

```sql
FROM leads l
LEFT JOIN crm   c ON c.lead_id = l.id      -- single user
LEFT JOIN audit a ON a.lead_id = l.id
```

becomes:

```sql
FROM leads l
LEFT JOIN lead_state s ON s.lead_id = l.id AND s.account_id = @account
LEFT JOIN audit      a ON a.lead_id = l.id          -- audit stays global
```

That's the *whole* shape of the migration: swap `crm` → `lead_state` and add
`AND ... = @account` to its join. The existing `audit`/filter code is untouched.

**Security rule:** `@account` comes from the authenticated session, **never** from
a query param. Every write checks `account_id` too. In Postgres, enforce it with
Row-Level Security so a missing `WHERE` can't leak across tenants.

---

## Migration path (low-risk, staged)

1. **Add `account_id` everywhere, default a single "personal" account.** Rename
   `crm` → `lead_state`, backfill `account_id = '<you>'`. App still works; you're
   now tenant #1. *(One migration, no behavior change.)*
2. **Add auth + `accounts`/`users`.** Resolve `@account` from session. Swap the
   join as above.
3. **Add `lists` / `list_items`.** Lists are just saved filters; `filter_json`
   can store the same query params the UI already builds (`?city=...&audit=bad`).
4. **Add `activity` timeline.** Write a row on every status change / note / call.
5. **When SQLite gets tight** (concurrent writers, >~10 accounts): move to
   Postgres, turn on RLS, keep the schema. Reads/writes are already
   account-scoped, so it's a lift-and-shift.

---

## Where the data pipeline fits

- **Leads & audit stay global and refresh centrally.** Your scraper agent +
  `audit_ci.py` keep the shared catalog current for *all* tenants at once — that's
  the platform's core asset and moat. Tenants never run scrapers; they consume.
- **Per-account data sources (later):** if a customer uploads their own leads,
  add `account_id` (nullable) to `leads` — `NULL` = the shared global catalog,
  non-null = that account's private import. The join above already filters
  correctly if you add `AND (l.account_id IS NULL OR l.account_id = @account)`.

---

## What this unlocks for the business

- **Sell the filtered view, not raw data.** "Bad-website salons in your county,
  with phone numbers and a ready pitch" is the product. The multi-tenant layer is
  what lets you charge per seat/account for it.
- **Agency tier** falls out naturally: one `account` with many `users`, shared
  lists and pipeline.
- **Usage metering** (leads viewed/exported per account) hangs off `activity`.
