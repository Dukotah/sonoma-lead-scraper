# SimplyTC Lead Engine — Design & Approach

**Goal:** Build SimplyTC (simplytc.com) a steady supply of *enriched, CRM-ready*
prospect data: real-estate **brokerages and high-volume agents/teams** who do
enough deals to need a transaction coordinator (TC), and who are **not already
locked in with a competing TC company**.

This document is the plan. It reuses ~80% of the existing toolkit in this repo
(originally built to find businesses that need websites) and replaces the parts
that are specific to that old use case.

---

## 1. What "really good data" means here

A row is only valuable to your mom if it answers three questions *before* she dials:

| # | Question | Why it matters | We answer it with… |
|---|----------|----------------|--------------------|
| 1 | **Is this the right kind of business?** | TCs serve brokerages, teams, and producing agents — not random offices. | Category filter (`real_estate` / `estate_agent`) + chain/franchise handling |
| 2 | **Do they do enough volume to need a TC?** | A 2-deals-a-year agent won't pay for a TC. A 5–50 agent brokerage almost always needs help. | **Volume proxies**: agent-roster size, listing count, team page (§4) |
| 3 | **Are they already using a competitor?** | Calling someone mid-contract with another TC company wastes the call. | **Competitor suppression list + TC-presence fingerprint** (§5) — *the hard part* |

Everything below is built to fill those three columns with a confidence score,
so a call list can be sorted best-first.

> **Honesty up front:** Question 3 is a *negative* signal — proving someone
> *doesn't* use a TC is impossible from public data alone. We can do two things
> well: (a) **confirm** the obvious "already taken" cases and remove them, and
> (b) **score the likelihood** of a gap. The rest is qualified on the call.
> Anyone who promises a clean "no TC" flag from scraping is guessing.

---

## 2. Ideal Customer Profile (ICP)

The tunable definition lives in [`config.py`](./config.py). Starting point:

- **Org types:** independent & mid-size brokerages, real-estate teams, top
  producing solo agents.
- **Sweet spot:** **5–50 agents**, independent or small-franchise. Big enough to
  have transaction volume, small enough to *not* have a salaried in-house TC team
  or corporate transaction-management built in.
- **Lower priority (often already covered):** national franchise corporate
  offices (Compass, eXp, KW Worldwide) — many bundle transaction management, so
  they're suppressed-by-default but kept with a flag, not deleted.
- **Geography:** national, swept **metro-by-metro** (see §3 — you don't query
  "the USA" in one shot; you run a target-market list).

---

## 3. Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │  config.py   ICP · target markets · competitor│
                 │              seeds · TC fingerprints          │
                 └─────────────────────────────────────────────┘
                                     │
   ┌──────────────┐   ┌──────────────────────┐   ┌────────────────────┐
   │ 1. COLLECT   │ → │ 2. ENRICH            │ → │ 3. SCORE & SUPPRESS │ → CSV/XLSX
   │ brokerages   │   │ volume + TC signals  │   │ TC-fit + competitor │   per market
   └──────────────┘   └──────────────────────┘   └────────────────────┘
```

### Stage 1 — Collect the universe (reuse, retarget)
The free national sources are **already wired up** in this repo:

- **Overture Maps** (`data-kit/download_sonoma.py`) — Meta/MSFT/Amazon open Places
  dataset, national, CC-BY. Filter `category_primary LIKE '%real_estate%'`. This
  is the **primary national source**. Run it per bbox/metro from the target list.
- **OpenStreetMap / Overpass** (`scraper-gui/app.py`, `office=estate_agent`) — the
  "Real Estate" niche already exists. Good live top-up, sparser coverage.
- *(Phase 2)* **State license databases** — each state's DRE/REC publishes
  licensee + broker-of-record data. Authoritative for the broker's legal name and
  decision-maker, but ~50 heterogeneous sources → deferred to phase 2.

**Key change from the old tool:** the old `osm_to_lead()` *drops* anything with a
`brand` tag (franchises were bad web-design leads). For TC we **keep** franchises
but **flag** them, because a franchised *office* can still be an independent
brokerage that needs a TC. We change the chain filter from "delete" to "label".

### Stage 2 — Enrich (extend existing audit)
Reuse `data-kit/lead_tools.py::audit_website()` plumbing, but fetch a few pages
per brokerage (home + `/agents`, `/team`, `/about`, `/listings`) and extract:

- **Agent-roster size** → volume proxy (counts agent cards / profile links).
- **In-house TC / TM software fingerprint** → see §5.
- **Decision-maker name** → broker/owner/office-manager from the About/Team page.
- **Best phone + contact path** → office line, "contact" page.

`web_verify()` (DuckDuckGo search in `lead_tools.py`) is reused to find a
brokerage's real site when Overture/OSM only has a directory link.

### Stage 3 — Score, suppress, export
- **Suppress** confirmed competitor clients (§5.1).
- **Score** TC-fit = volume signal + gap likelihood (§6).
- **Export** the same dual output the kit already produces: a pretty `.xlsx` for
  reviewing and a **CRM-ready `.csv`** (`enrich_leads.py::write_outputs()`), with
  columns re-mapped to what a TC business actually calls on (§7).

---

## 4. Qualifying volume (free signals)

Without paid MLS access we use proxies, combined into a `volume_score`:

| Signal | Source | Strength |
|--------|--------|----------|
| **# agents on roster page** | scrape `/agents`, `/our-team` | strong — more agents ≈ more transactions |
| **# active listings shown** | scrape `/listings` / `/properties` | medium — current pipeline size |
| **"Team" / "Group" in name** | name string | weak — teams usually have volume |
| **Multiple office locations** | count Overture/OSM POIs sharing the brand/name | medium |
| **Brokerage vs solo** | `office=estate_agent` POI vs agent profile | structural |

A brokerage with 12 agents and 30 listings is a far better call than a solo agent
with a Wix page — and the score reflects that.

---

## 5. The hard part: "not already using a competitor"

Two complementary mechanisms.

### 5.1 Competitor suppression list (confirm & remove)
Many outsourced-TC companies publish **testimonials, client logos, and
"agents/brokerages we serve"** pages. We scrape a seed list of known TC companies
(in [`config.py`](./config.py) → `COMPETITOR_TC_SEEDS`, *user-verified*) and build
a suppression set of named brokerages/agents. Anyone matching it is flagged
`already_has_tc = confirmed` and dropped to the bottom (kept, not deleted, so you
can re-approach when a contract lapses).

> The seed list ships with placeholders to **verify and expand** — don't trust
> vendor names you didn't confirm. This is curated data, not a guess.

### 5.2 TC-presence fingerprint (score the gap)
While auditing each brokerage site (§2) we look for tells that they *already*
handle coordination — in-house or via software:

- **Outsourced/in-house TC mentions:** "transaction coordinator", "our TC",
  "transaction management", a named TC on the team page.
- **TM software fingerprints in page HTML/links:** SkySlope, Dotloop, Paperless
  Pipeline, Brokermint, etc. (see `config.py → TC_SOFTWARE_FINGERPRINTS`).
- **Hiring an in-house TC** *(phase 2)*: a careers page posting for a TC ⇒ they
  do it internally.

Result is a `tc_gap` verdict: `open` (no signal — best leads), `software`
(uses TM software but maybe no human TC — still pitchable), `in_house` /
`confirmed_competitor` (lowest priority).

This mirrors how the old tool fingerprinted *website builders* (`audit_website`'s
`builder` detection) — we're just fingerprinting **TC tooling** instead.

---

## 6. Scoring model

`tc_fit_score = volume_score + gap_score + contactability − suppression_penalty`

| Component | Range | Notes |
|-----------|------:|-------|
| `volume_score` | 0–50 | roster size, listings, multi-office (§4) |
| `gap_score` | 0–40 | `open`=40, `software`=20, `in_house`=5, `confirmed`=0 |
| `contactability` | 0–10 | has direct phone + named decision-maker |
| `suppression_penalty` | −100 | on confirmed competitor client → sinks to bottom |

Output tiers (replacing the old website-quality A/B/C):

- **Tier A — Call first:** good volume + open TC gap + reachable.
- **Tier B — Worth a call:** volume but uses software, or volume unknown but open gap.
- **Tier C — Later / re-approach:** low volume, or confirmed competitor (revisit on contract churn).

Scoring lives in [`score.py`](./score.py), adapted from `lead_tools.py::score_lead()`.

---

## 7. CRM-ready output columns

A generic CSV that imports into any CRM (HubSpot, GoHighLevel, Pipedrive, a Sheet).
Built by extending `enrich_leads.py::write_outputs()`:

```
Company name, Brokerage type, Decision-maker, Title, Phone, Email, Website,
City, State, Address, # Agents (est.), # Listings (est.),
TC gap, Already has TC?, Volume score, TC-fit score, Tier,
Why a lead, Suggested opener, Source, Source URL, Last verified
```

`Suggested opener` is the SimplyTC analog of the old `pitch_for()` — e.g.
*"18-agent independent brokerage, no TC software detected — open: do your agents
still do their own contract-to-close paperwork?"*

---

## 8. Legal / ethical guardrails (read before calling)

This is legitimate B2B prospecting from public data, but:

- **Use the clean sources.** Overture (CC-BY), OSM (ODbL — attribute), and public
  license registries are fine. Avoid scraping sites that forbid it in their ToS
  (Zillow, LinkedIn, Realtor.com aggressively block and prohibit it). Where we hit
  a brokerage's *own* site we fetch politely (cached, rate-limited, real UA — the
  kit already does this).
- **Calling rules.** B2B calls to a published business line are broadly permitted,
  but scrub any **mobile/personal** numbers against the **National Do-Not-Call
  registry** and honor TCPA/state rules. Keep an opt-out/suppression list.
- **Attribution.** Overture → credit "Overture Maps Foundation"; OSM → "© OpenStreetMap contributors".
- **Don't store more than you'll use.** Names + business contact + public signals. No scraping of private data.

---

## 9. Build phases

- **Phase 0 (this doc + scaffold):** ✅ approach, ICP config, module stubs.
- **Phase 1 — MVP (one market):** retarget Overture/OSM to brokerages in 1–2 metros;
  roster-size enrichment; competitor suppression v1; TC fingerprint v1; scored CSV.
  → Validate with your mom on ~50 real calls: *does this data make her calls better?*
- **Phase 2 — Scale:** target-market sweep (top N metros), state license-DB
  collectors for decision-maker names, careers-page TC detection, dedupe against
  her existing CRM so she never gets a dupe.
- **Phase 3 — Operate:** scheduled refresh, "new brokerage" alerts, contract-churn
  re-approach queue, direct CRM push.

---

## 10. Open decisions for you

1. **First metro(s)** to validate on (Phase 1 needs a real target market).
2. **Known competitors** to seed `COMPETITOR_TC_SEEDS` — you/your mom know the real
   names in her market; that makes suppression far more accurate.
3. **CRM** she'll actually use — we default to a universal CSV until you pick one.
4. **Volume bar** — minimum agent count worth calling (default ≥5).
```
