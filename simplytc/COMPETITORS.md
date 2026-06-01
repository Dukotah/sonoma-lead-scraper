# Competitor transaction-coordination companies

Research compiled June 2026 to seed the **competitor-suppression** list (so the
tool skips brokerages already using a rival TC). These are wired into
`leadgen/verticals/simply_tc.py` → `CONFIG["competitor_tc_seeds"]`.

> **Verify before trusting.** Web pages change. The suppression scraper only
> helps when a competitor actually publishes named client/agent/brokerage
> testimonials. Review the names it pulls before relying on them, and prune any
> company here that isn't a real rival in your mom's market.

## Direct / regional (California & Sonoma County) — highest priority
| Company | Site | Why it matters |
|---|---|---|
| **Real Estate Paper Pushers** | realestatepaperpushers.com | **Most direct rival** — explicitly serves **Sonoma County**; 4.9★, names agents in testimonials (John C., Christine M., Jerald H., Jackie M.). |
| California TC | californiatc.net | Virtual TC covering California statewide. |
| Daniela Santana (CAR Certified TC) | (find site) | Full-time virtual TC across California — regional solo rival. |

## National players (publish agent/brokerage testimonials)
| Company | Site |
|---|---|
| Coordinator Team | coordinatorteam.com |
| Premier TC Services | premiertcsvc.com |
| Transactly | transactly.com |
| XACT-TC | xact-tc.com |
| Be Happy TC | behappytc.com |
| AgentUp | agentup.com |
| MyOutDesk | myoutdesk.com/services/transaction-coordinator |
| Freedom RES | freedom-res.com |
| TCTor | tctor.com |
| Taylor TC Services (TN) | taylortcexpert.com |
| Real Estate Paper Pushers (Paper Pushers, Inc.) | mypaperpushers.com |

## Transaction-management SOFTWARE (different signal)
These aren't TC *companies* but TC *software*. A brokerage using one may still
lack a human coordinator — so they're scored as a "software" gap (pitchable),
not suppressed. Fingerprinted in `CONFIG["tc_software"]`:
SkySlope, Dotloop, Paperless Pipeline, Brokermint, TransactionDesk, Open To Close.

## How to add or remove a competitor
Edit `leadgen/verticals/simply_tc.py`:
```python
"competitor_tc_seeds": {
    "their_label": "https://their-site.com/testimonials",  # add a line
    # delete a line to stop suppressing that company's clients
},
```
Or, in the GUI, paste competitor testimonial URLs into the
**"Skip competitors' clients"** box for a one-off run (no code edit needed).

## Sources
- AgentUp competitor roundups: https://www.agentup.com/blog/virtual-real-estate-transaction-coordinator-companies
- Real Estate Paper Pushers — Sonoma County: https://realestatepaperpushers.com/California/Sonoma-County
- Birdeye reviews (named agents): https://reviews.birdeye.com/real-estate-paper-pushers-148642105991442
- Coordinator Team: https://coordinatorteam.com/ · Premier TC: https://www.premiertcsvc.com/ · Transactly: https://transactly.com/
