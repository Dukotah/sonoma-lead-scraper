"""
Realistic brokerage-website HTML fixtures for testing the enrichment heuristics
offline. Each mimics a real-world scenario the extractors must handle:

  BIG_SOFTWARE   large brokerage, agent roster, uses SkySlope (software TC gap)
  SMALL_OPEN     small brokerage, broker/owner named, no TC signal (the hot lead)
  IN_HOUSE_TC    brokerage with a named in-house transaction coordinator
  HIRING_TC      brokerage advertising to HIRE a TC (a gap — they need help now)
  SOLO_AGENT     single agent, minimal site
  DUP_LINKS      roster where every agent is linked twice (photo + name) — the
                 classic over-count trap the agent estimator must avoid
"""

BIG_SOFTWARE = """
<html><head><title>Coastal Realty Group — Sonoma County</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body>
<nav><a href="/agents">Our Agents</a><a href="/listings">Listings</a></nav>
<section class="agents">
  <div class="agent-card"><a href="/agents/jane-smith/"><img src="/img/jane.jpg" alt="Jane Smith"></a>
     <h3><a href="/agents/jane-smith/">Jane Smith</a></h3><p>DRE #01234567</p></div>
  <div class="agent-card"><a href="/agents/bob-lee/"><img src="/img/bob.jpg" alt="Bob Lee"></a>
     <h3><a href="/agents/bob-lee/">Bob Lee</a></h3><p>DRE #01234568</p></div>
  <div class="agent-card"><a href="/agents/maria-gomez/"><img alt="Maria Gomez"></a>
     <h3><a href="/agents/maria-gomez/">Maria Gomez</a></h3><p>CalBRE #01234569</p></div>
  <div class="agent-card"><a href="/agents/tom-ng/"><img alt="Tom Ng"></a>
     <h3><a href="/agents/tom-ng/">Tom Ng</a></h3><p>DRE# 01234570</p></div>
  <div class="agent-card"><a href="/agents/sara-kim/"><img alt="Sara Kim"></a>
     <h3><a href="/agents/sara-kim/">Sara Kim</a></h3><p>DRE #01234571</p></div>
</section>
<footer>Transactions managed with SkySlope. © Coastal Realty Group</footer>
</body></html>
"""

SMALL_OPEN = """
<html><head><title>Harbor Real Estate</title></head><body>
<h1>Harbor Real Estate</h1>
<div class="about">
  <p>Founded in 2009, Harbor Real Estate is a boutique brokerage serving Petaluma.</p>
  <p>Susan Park, Broker/Owner — DRE #00987654</p>
</div>
<section class="team">
  <div class="agent"><a href="/team/susan-park">Susan Park</a> — Broker/Owner</div>
  <div class="agent"><a href="/team/david-cho">David Cho</a> — Realtor</div>
  <div class="agent"><a href="/team/ana-ruiz">Ana Ruiz</a> — Realtor</div>
</section>
<footer>Contact us at info@harborre.com</footer>
</body></html>
"""

IN_HOUSE_TC = """
<html><head><title>Summit Brokerage</title></head><body>
<section class="team">
  <h2>Meet Our Team</h2>
  <div class="member"><a href="/team/greg-hall">Greg Hall</a> — Managing Broker</div>
  <div class="member"><a href="/team/lisa-monroe">Lisa Monroe</a> — Transaction Coordinator</div>
  <div class="member"><a href="/team/kyle-d">Kyle Daniels</a> — Realtor</div>
</section>
<p>Our in-house transaction coordinator handles every file from contract to close.</p>
</body></html>
"""

HIRING_TC = """
<html><head><title>Vanguard Properties — Careers</title></head><body>
<h1>Join Our Team</h1>
<div class="job-posting">
  <h2>We are hiring a Transaction Coordinator</h2>
  <p>Vanguard Properties is seeking an experienced transaction coordinator to
     support our growing team of agents. Apply today!</p>
</div>
<section class="agents">
  <div class="agent-card"><a href="/agents/p1">Agent One</a></div>
  <div class="agent-card"><a href="/agents/p2">Agent Two</a></div>
  <div class="agent-card"><a href="/agents/p3">Agent Three</a></div>
  <div class="agent-card"><a href="/agents/p4">Agent Four</a></div>
</section>
</body></html>
"""

SOLO_AGENT = """
<html><head><title>John Realtor — Santa Rosa Homes</title></head><body>
<h1>John Realtor</h1><p>Your trusted Santa Rosa agent. DRE #01112223</p>
<a href="/contact">Contact</a>
</body></html>
"""

# Every agent appears as TWO links (image + name) — naive link-counting doubles it.
DUP_LINKS = """
<html><body><section class="roster">
  <div class="card"><a href="/agents/aa/"><img alt="Agent AA"></a><a href="/agents/aa/">Agent AA</a></div>
  <div class="card"><a href="/agents/bb/"><img alt="Agent BB"></a><a href="/agents/bb/">Agent BB</a></div>
  <div class="card"><a href="/agents/cc/"><img alt="Agent CC"></a><a href="/agents/cc/">Agent CC</a></div>
</section></body></html>
"""

# Competitor testimonial page (for suppression tests)
COMPETITOR_TESTIMONIALS = """
<html><body>
<h1>What our clients say</h1>
<blockquote>"They transformed our closings!" — Jane Doe, Coastal Realty Group</blockquote>
<blockquote>"Best decision we made." — Mark Lin, Summit Brokerage</blockquote>
<div class="logos">
  <img alt="Harbor Real Estate" src="/l1.png">
  <img alt="Pinnacle Properties" src="/l2.png">
</div>
</body></html>
"""

ALL = {
    "BIG_SOFTWARE": BIG_SOFTWARE, "SMALL_OPEN": SMALL_OPEN, "IN_HOUSE_TC": IN_HOUSE_TC,
    "HIRING_TC": HIRING_TC, "SOLO_AGENT": SOLO_AGENT, "DUP_LINKS": DUP_LINKS,
    "COMPETITOR_TESTIMONIALS": COMPETITOR_TESTIMONIALS,
}
