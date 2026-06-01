# Sonoma County Business Leads — Data Dictionary

**4,779 businesses** across **681 niches** and **80 cities** in Sonoma County, CA.

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
| `phone` | 94% | Primary phone, raw. |
| `phone_fmt` | 94% | Primary phone, formatted (XXX) XXX-XXXX when it's a valid 10-digit US number. |
| `area_code` | 94% | 3-digit area code of the primary phone. |
| `phones_all` | 94% | All listed phone numbers, pipe-separated. |
| `email` | 44% | Primary email (only ~41% of leads have one). |
| `email_owned` | 100% | 1 if the email's domain matches the website domain (owned, not a gmail/yahoo). |
| `website` | 76% | Primary website URL (empty for ~17% = Tier A 'no site' leads). |
| `websites_all` | 76% | All listed website URLs, pipe-separated. |
| `socials` | 69% | All social profile URLs, pipe-separated. |
| `social_platforms` | 69% | Which platforms are present, pipe-separated (facebook|instagram|...). |
| `best_contact` | 100% | Suggested channel: phone | email | social | none. |
| `address` | 97% | Street address (freeform). |
| `city` | 100% | City. |
| `state` | 99% | State (CA). |
| `zip` | 97% | Postal code. |
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
- A (no real website — hottest): 1,210
- B (DIY builder site — upsell): 72
- C (has a real website): 3,497

**industry_fit** (likelihood the niche buys web design):
- high: 1,940  ·  medium: 2,400  ·  low: 439

**Ranking tip:** sort by `outreach_score` (desc) for a cold-call queue. `tier='A'` + `industry_fit='high'` + a phone = your warmest segment.

## Top 25 niches

| Niche | Count |
|---|---|
| winery | 130 |
| real_estate_agent | 113 |
| beauty_salon | 84 |
| community_services_non_profits | 82 |
| automotive_repair | 69 |
| church_cathedral | 68 |
| hotel | 68 |
| farm | 64 |
| gas_station | 53 |
| doctor | 47 |
| flowers_and_gifts_shop | 45 |
| elementary_school | 44 |
| bed_and_breakfast | 43 |
| mexican_restaurant | 41 |
| campground | 40 |
| hair_salon | 40 |
| contractor | 39 |
| restaurant | 39 |
| grocery_store | 38 |
| gym | 36 |
| public_and_government_association | 34 |
| professional_services | 33 |
| skate_park | 31 |
| art_gallery | 29 |
| religious_organization | 29 |
