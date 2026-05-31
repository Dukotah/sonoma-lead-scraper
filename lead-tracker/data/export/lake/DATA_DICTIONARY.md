# Sonoma County Business Leads — Data Dictionary

**2,737 businesses** across **533 niches** and **59 cities** in Sonoma County, CA.

Source: [Overture Maps](https://overturemaps.org) (CC-BY 4.0), cleaned, de-chained, and enriched. No web scraping.

## Files

| File | What |
|---|---|
| `sonoma_leads_full.csv` | All leads, all columns (import this into the CRM). |
| `sonoma_leads_full.jsonl` | Same data, one JSON object per line. |
| `niches.csv` | Every niche with its count. |
| `cities.csv` | Every city with its count. |
| `DATA_DICTIONARY.md` | This file. |

## Suggested CRM schema

`id` is a stable unique key — use it as the primary key so re-imports upsert cleanly. All fields are text unless noted.

| Column | Fill % | Description |
|---|---|---|
| `id` | 100% | Stable unique ID (from Overture Maps). Use as the CRM primary key. |
| `name` | 100% | Business name. |
| `category` | 96% | Primary niche/sector (Overture taxonomy, e.g. beauty_salon, restaurant). |
| `alt_categories` | 65% | Other categories that also apply, pipe-separated. |
| `phone` | 93% | Primary phone, raw. |
| `phone_fmt` | 93% | Primary phone, formatted (XXX) XXX-XXXX when it's a valid 10-digit US number. |
| `area_code` | 93% | 3-digit area code of the primary phone. |
| `phones_all` | 93% | All listed phone numbers, pipe-separated. |
| `email` | 41% | Primary email (only ~41% of leads have one). |
| `email_owned` | 100% | 1 if the email's domain matches the website domain (owned, not a gmail/yahoo). |
| `website` | 74% | Primary website URL (empty for ~17% = Tier A 'no site' leads). |
| `websites_all` | 74% | All listed website URLs, pipe-separated. |
| `socials` | 69% | All social profile URLs, pipe-separated. |
| `social_platforms` | 69% | Which platforms are present, pipe-separated (facebook|instagram|...). |
| `best_contact` | 100% | Suggested channel: phone | email | social | none. |
| `address` | 96% | Street address (freeform). |
| `city` | 99% | City. |
| `state` | 99% | State (CA). |
| `zip` | 96% | Postal code. |
| `country` | 100% | Country code. |
| `lat` | 100% | Latitude. |
| `lon` | 100% | Longitude. |
| `tier` | 100% | Website-need tier: A=no/social-only site, B=DIY builder site, C=real custom site. |
| `tier_reason` | 100% | Human-readable explanation of the tier. |
| `builder` | 2% | Detected DIY builder (Wix/Weebly/etc.) for Tier B; empty otherwise. |
| `industry_fit` | 100% | How likely the niche buys web design: high | medium | low. |
| `outreach_score` | 100% | 0-100 cold-outreach priority (need + reachability + fit). Best ranking field for a call queue. |
| `score` | 100% | 0-100 raw lead-priority (need + reachability + confidence), ignores industry fit. |
| `completeness` | 100% | 0-100 how filled-in this record is. |
| `confidence` | 100% | Overture's 0-1 confidence that this place exists/is accurate. |
| `is_chain` | 100% | 1 if flagged as a chain/franchise (these were mostly already excluded). |
| `pitch` | 100% | A personalized one-line cold-open, tailored to tier/niche/city. |
| `source_dataset` | 100% | Which Overture source this record came from. |
| `source_id` | 100% | Record ID within that source. |

## Key value distributions

**tier** (website need):
- A (no real website — hottest): 749
- B (DIY builder site — upsell): 54
- C (has a real website): 1,934

**industry_fit** (likelihood the niche buys web design):
- high: 1,139  ·  medium: 1,349  ·  low: 249

**Ranking tip:** sort by `outreach_score` (desc) for a cold-call queue. `tier='A'` + `industry_fit='high'` + a phone = your warmest segment.

## Top 25 niches

| Niche | Count |
|---|---|
| winery | 170 |
| real_estate_agent | 71 |
| church_cathedral | 51 |
| community_services_non_profits | 51 |
| farm | 46 |
| automotive_repair | 43 |
| beauty_salon | 42 |
| doctor | 34 |
| hotel | 31 |
| gas_station | 28 |
| hair_salon | 26 |
| campground | 25 |
| coffee_shop | 25 |
| grocery_store | 24 |
| rv_park | 23 |
| professional_services | 22 |
| contractor | 21 |
| gym | 21 |
| restaurant | 21 |
| bed_and_breakfast | 20 |
| elementary_school | 20 |
| medical_center | 20 |
| mexican_restaurant | 18 |
| self_storage_facility | 18 |
| convenience_store | 17 |
