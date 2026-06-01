# Sonoma County Business Leads — Data Dictionary

**14,868 businesses** across **1,066 niches** and **107 cities** in Sonoma County, CA.

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
| `category` | 94% | Primary niche/sector (Overture taxonomy, e.g. beauty_salon, restaurant). |
| `alt_categories` | 59% | Other categories that also apply, pipe-separated. |
| `phone` | 95% | Primary phone, raw. |
| `phone_fmt` | 95% | Primary phone, formatted (XXX) XXX-XXXX when it's a valid 10-digit US number. |
| `area_code` | 95% | 3-digit area code of the primary phone. |
| `phones_all` | 95% | All listed phone numbers, pipe-separated. |
| `email` | 40% | Primary email (only ~41% of leads have one). |
| `email_owned` | 100% | 1 if the email's domain matches the website domain (owned, not a gmail/yahoo). |
| `website` | 86% | Primary website URL (empty for ~17% = Tier A 'no site' leads). |
| `websites_all` | 86% | All listed website URLs, pipe-separated. |
| `socials` | 55% | All social profile URLs, pipe-separated. |
| `social_platforms` | 55% | Which platforms are present, pipe-separated (facebook|instagram|...). |
| `best_contact` | 100% | Suggested channel: phone | email | social | none. |
| `address` | 97% | Street address (freeform). |
| `city` | 100% | City. |
| `state` | 100% | State (CA). |
| `zip` | 98% | Postal code. |
| `country` | 100% | Country code. |
| `lat` | 100% | Latitude. |
| `lon` | 100% | Longitude. |
| `tier` | 100% | Website-need tier: A=no/social-only site, B=DIY builder site, C=real custom site. |
| `tier_reason` | 100% | Human-readable explanation of the tier. |
| `builder` | 1% | Detected DIY builder (Wix/Weebly/etc.) for Tier B; empty otherwise. |
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
- A (no real website — hottest): 2,203
- B (DIY builder site — upsell): 99
- C (has a real website): 12,566

**industry_fit** (likelihood the niche buys web design):
- high: 6,330  ·  medium: 7,720  ·  low: 818

**Ranking tip:** sort by `outreach_score` (desc) for a cold-call queue. `tier='A'` + `industry_fit='high'` + a phone = your warmest segment.

## Top 25 niches

| Niche | Count |
|---|---|
| real_estate_agent | 569 |
| doctor | 200 |
| hair_salon | 196 |
| community_services_non_profits | 195 |
| beauty_salon | 166 |
| winery | 164 |
| professional_services | 160 |
| automotive_repair | 158 |
| gym | 151 |
| contractor | 149 |
| restaurant | 148 |
| church_cathedral | 124 |
| dentist | 117 |
| clothing_store | 102 |
| real_estate | 101 |
| medical_center | 99 |
| financial_service | 95 |
| art_gallery | 93 |
| insurance_agency | 91 |
| nail_salon | 87 |
| chiropractor | 84 |
| coffee_shop | 81 |
| counseling_and_mental_health | 80 |
| mexican_restaurant | 80 |
| spas | 79 |
