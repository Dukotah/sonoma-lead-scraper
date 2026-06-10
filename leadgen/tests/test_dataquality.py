"""
Tests for the data-quality layer: value normalization (names, phones, emails,
websites), the derived CRM rollups (email_owned / best_contact / completeness),
contact extraction from enriched pages, homepage link discovery, and website-host
deduplication. All offline.

Run:  python leadgen/tests/test_dataquality.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from leadgen.normalize import (clean_name, normalize_phone, clean_email,
                               email_owned, normalize_website, social_platform,
                               best_contact, completeness, normalize_record,
                               finalize_record)
from leadgen.enrich import extract_emails, extract_phones, _discover_links
from leadgen.pipeline import _dedupe


# ─────────────────────────────── names ───────────────────────────────────────
def test_clean_name_fixes_shouting_keeps_acronyms():
    assert clean_name("  JOHN   REALTOR ") == "John Realtor"
    assert clean_name("COASTAL REALTY GROUP") == "Coastal Realty Group"
    assert clean_name("Acme Realty, LLC") == "Acme Realty, LLC"   # mixed case untouched
    assert clean_name("Harbor Real Estate") == "Harbor Real Estate"
    assert clean_name("") == ""


# ─────────────────────────────── phones ──────────────────────────────────────
def test_normalize_phone_us_formats():
    assert normalize_phone("707-555-0102") == ("(707) 555-0102", "707")
    assert normalize_phone("+1 (415) 555.0144") == ("(415) 555-0144", "415")
    assert normalize_phone("17075550102") == ("(707) 555-0102", "707")


def test_normalize_phone_non_us_passthrough():
    fmt, area = normalize_phone("+44 20 7946 0958")
    assert area == "" and "44" in fmt
    assert normalize_phone("") == ("", "")


# ─────────────────────────────── emails ──────────────────────────────────────
def test_clean_email_validates_and_drops_noise():
    assert clean_email("  Info@Harborre.COM ") == "info@harborre.com"
    assert clean_email("noreply@acme.com") == ""       # system mailbox
    assert clean_email("not-an-email") == ""
    assert clean_email("jane@example.com") == ""        # placeholder domain


def test_email_owned():
    assert email_owned("jane@acme.com", "https://www.acme.com") == 1
    assert email_owned("jane@acme.com", "http://acme.com/about") == 1
    assert email_owned("jane@gmail.com", "https://acme.com") == 0
    assert email_owned("", "https://acme.com") == 0


# ─────────────────────────────── websites ────────────────────────────────────
def test_normalize_website_canonicalizes():
    assert normalize_website("ACME.com") == "http://acme.com"
    assert normalize_website("https://Acme.com/About/#team") == "https://acme.com/About"
    assert normalize_website("http://acme.com/") == "http://acme.com"
    assert normalize_website("") == ""


def test_social_platform_detection():
    assert social_platform("https://facebook.com/acme") == "facebook"
    assert social_platform("http://www.instagram.com/acme") == "instagram"
    assert social_platform("https://acme.com") == ""


# ───────────────────────── derived rollups ───────────────────────────────────
def test_best_contact_priority():
    assert best_contact({"phone": "(707) 555-0102", "email": "a@b.com"}) == "phone"
    assert best_contact({"email": "a@b.com"}) == "email"
    assert best_contact({"website": "https://facebook.com/acme"}) == "social"
    assert best_contact({"website": "https://acme.com"}) == "none"
    assert best_contact({}) == "none"


def test_completeness_and_finalize():
    rec = {"name": "Acme", "phone": "707-555-0102", "email": "jane@acme.com",
           "website": "https://www.acme.com", "address": "1 Main", "city": "Santa Rosa",
           "state": "CA", "zip": "95401", "lat": 38.4}
    normalize_record(rec)
    finalize_record(rec)
    assert rec["phone_fmt"] == "(707) 555-0102" and rec["area_code"] == "707"
    assert rec["email_owned"] == 1
    assert rec["best_contact"] == "phone"
    assert rec["completeness"] == 100               # every weighted field present
    thin = {"name": "Bare Co"}
    finalize_record(thin)
    assert thin["best_contact"] == "none" and thin["completeness"] == 10


# ───────────────────── contact extraction from pages ─────────────────────────
def test_extract_emails_prefers_owned_and_drops_noise():
    pages = {"http://acme.com": (
        "<a href='mailto:noreply@acme.com'>x</a> "
        "Reach the broker at Jane@Acme.com or our assistant help@gmail.com")}
    got = extract_emails(pages, prefer_host="acme.com")
    assert got[0] == "jane@acme.com"                # owned domain ranks first
    assert "noreply@acme.com" not in got            # system mailbox dropped
    assert "help@gmail.com" in got


def test_extract_phones_dedupes_and_finds():
    pages = {"x": "Call (707) 555-0102 or 707.555.0102 today. Fax 1-415-555-0144."}
    got = extract_phones(pages)
    assert len(got) == 2                            # the two 707s collapse to one
    assert any("0144" in p for p in got)


# ──────────────────────── homepage link discovery ───────────────────────────
def test_discover_links_finds_team_contact_on_same_host():
    home = """
      <a href="/our-realtors">Meet the Agents</a>
      <a href="/contact-us">Contact</a>
      <a href="https://facebook.com/acme">Facebook</a>
      <a href="/listings">Homes</a>
    """
    links = _discover_links(home, "http://acme.com")
    assert any("our-realtors" in u for u in links)
    assert any("contact-us" in u for u in links)
    assert not any("facebook.com" in u for u in links)   # off-site skipped
    assert not any("listings" in u for u in links)        # not a roster/contact link


# ───────────────────────── website-host dedupe ──────────────────────────────
def test_dedupe_merges_on_shared_website_host():
    leads = [
        {"name": "Acme Realty", "city": "Santa Rosa",
         "website": "http://acme.com", "phone": "(707) 555-0102", "email": ""},
        {"name": "Acme Real Estate of the North Bay", "city": "Petaluma",
         "website": "https://www.acme.com/about", "phone": "", "email": "jane@acme.com"},
    ]
    out = _dedupe(leads)
    assert len(out) == 1, "same website host = same business, even across names/cities"
    assert out[0]["email"] == "jane@acme.com"       # back-filled from the dupe


def _run_all():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(_run_all())
