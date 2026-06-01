"""
Lead Engine — web UI over the universal `leadgen` package.

Pick a vertical (what to prospect for) and a market (where), optionally paste
competitor pages to suppress, hit Run. Streams live progress and serves the
resulting CRM CSV + tiered XLSX for download. Also renders the top leads in-page.

Run:
    pip install -r gui/requirements.txt
    python gui/app.py            # then open the printed URL
    # or native window:  python gui/desktop_app.py
"""
import io
import os
import sys
import time
import socket
import threading
from datetime import datetime

from flask import Flask, request, jsonify, send_file, render_template_string

# Make the repo root importable so `import leadgen` works regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import leadgen
from leadgen import get_vertical, all_verticals, run_pipeline
from leadgen.geo import MARKETS
from leadgen.pipeline import load_crm_names
from leadgen.diagnostics import check_connectivity, friendly_error, explain_empty_result

app = Flask(__name__)

# In-memory job store: job_id -> {log, done, error, stats, leads, files}
JOBS: dict[str, dict] = {}
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_output")
os.makedirs(OUT_DIR, exist_ok=True)


# ───────────────────────────── job runner ────────────────────────────────────
def run_job(job_id: str, params: dict):
    job = JOBS[job_id]

    def log(msg):
        job["log"].append(f"[{datetime.now():%H:%M:%S}] {msg}")

    try:
        vertical = get_vertical(params["vertical"])
        demo = bool(params.get("demo"))
        market = (params.get("market") or "").strip() or ("(demo)" if demo else "")
        sources = tuple(params.get("sources") or ["overture"])
        enrich = bool(params.get("enrich", True))
        limit = params.get("limit") or None
        enrich_cap = params.get("enrich_cap") or 150

        override = {}
        comp = vertical.competitor_input
        urls = [u.strip() for u in (params.get("competitor_urls") or "").splitlines()
                if u.strip()]
        if comp and urls:
            override[comp["config_key"]] = urls
            log(f"Using {len(urls)} competitor page(s) for suppression.")

        # Existing-CRM dedupe: names pasted/uploaded so we never return a dupe.
        exclude = load_crm_names(params.get("crm_csv", ""), is_text=True) if params.get("crm_csv") else None
        if exclude:
            log(f"Loaded {len(exclude)} company names from your CRM — will skip those.")

        stem = os.path.join(
            OUT_DIR,
            f"{params['vertical']}_{_slug(market) or 'demo'}_{datetime.now():%Y%m%d_%H%M%S}")

        log(f"Vertical: {vertical.label}" + ("  (DEMO MODE)" if demo else ""))
        leads = run_pipeline(
            vertical, market,
            sources=sources, limit=limit, enrich=enrich, enrich_cap=enrich_cap,
            out_stem=stem, config_override=override or None,
            exclude_names=exclude, demo=demo, log=log,
        )

        files = run_pipeline.last_outputs  # (csv_path, xlsx_path) or None
        job["files"] = {
            "csv": os.path.basename(files[0]) if files else None,
            "xlsx": os.path.basename(files[1]) if files else None,
        }
        job["columns"] = vertical.columns
        # Keep a preview (top 50) for in-page rendering; full data is in the files.
        job["leads"] = leads[:50]
        job["stats"] = _tier_counts(leads, total=len(leads))
        if not leads:
            job["notice"] = explain_empty_result(market, sources, vertical.label)
            log(job["notice"])
        else:
            log(f"Done. {len(leads)} leads — download below.")
    except Exception as e:
        raw = f"{type(e).__name__}: {e}"
        job["error"] = friendly_error(str(e)) or raw
        log(f"ERROR: {job['error']}")
    finally:
        job["done"] = True


def _tier_counts(leads, total):
    n = {"A": 0, "B": 0, "C": 0}
    for r in leads:
        n[r.get("tier", "C")] = n.get(r.get("tier", "C"), 0) + 1
    return {"total": total, **n}


def _slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ───────────────────────────── routes ────────────────────────────────────────
@app.route("/")
def index():
    verts = [{"key": k, "label": v.label, "description": v.description,
              "competitor_input": v.competitor_input,
              "default_sources": ["osm"] if not v.overture_categories and v.osm_tags else ["overture"]}
             for k, v in sorted(all_verticals().items())]
    markets = sorted(MARKETS.keys())
    return render_template_string(INDEX_HTML, verticals=verts, markets=markets)


@app.route("/run", methods=["POST"])
def start_run():
    params = request.get_json(force=True)
    if not params.get("vertical"):
        return jsonify({"error": "vertical is required"}), 400
    if not params.get("demo") and not params.get("market"):
        return jsonify({"error": "market is required (or use Demo mode)"}), 400
    jid = str(int(time.time() * 1000))
    JOBS[jid] = {"log": [], "done": False, "error": None, "notice": None,
                 "stats": None, "leads": None, "files": None, "columns": None}
    threading.Thread(target=run_job, args=(jid, params), daemon=True).start()
    return jsonify({"job_id": jid})


@app.route("/check")
def check():
    """Connectivity self-check — probe every data source, plain-English status."""
    return jsonify(check_connectivity())


@app.route("/progress/<jid>")
def progress(jid):
    job = JOBS.get(jid)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify({
        "log": job["log"], "done": job["done"], "error": job["error"],
        "notice": job.get("notice"),
        "stats": job["stats"], "files": job["files"],
        "leads": job["leads"] if job["done"] and not job["error"] else None,
        "columns": job["columns"],
    })


@app.route("/download/<kind>/<jid>")
def download(kind, jid):
    job = JOBS.get(jid)
    if not job or not job.get("files"):
        return "Not ready", 404
    fname = job["files"].get(kind)
    if not fname:
        return "No such file", 404
    path = os.path.join(OUT_DIR, fname)
    if not os.path.exists(path):
        return "File missing", 404
    return send_file(path, as_attachment=True, download_name=fname)


# ───────────────────────────── server bootstrap ──────────────────────────────
def free_port(default=5000):
    for p in (default, 5001, 5050, 8000, 8080, 8765):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return default


INDEX_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Lead Engine</title>
<style>
:root{--blue:#1F4E78;--green:#28a745}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;
  max-width:1080px;margin:0 auto;padding:24px 18px;color:#1d2733;background:#fafbfc}
h1{margin:0 0 2px}.sub{color:#667;margin:0 0 18px;font-size:14px}
fieldset{border:1px solid #dde2e8;border-radius:10px;margin:0 0 16px;padding:14px 16px;background:#fff}
legend{padding:0 8px;font-weight:650;color:var(--blue)}
label.fld{display:block;font-size:13px;font-weight:600;margin:10px 0 4px;color:#445}
input[type=text],input[type=number],select,textarea{
  width:100%;padding:9px 10px;font-size:14px;border:1px solid #c4ccd6;border-radius:7px;font-family:inherit}
textarea{resize:vertical;min-height:74px}
.row{display:flex;gap:14px;flex-wrap:wrap}.row>div{flex:1;min-width:220px}
.hint{color:#8a93a0;font-size:12px;margin-top:4px}
.checks label{display:inline-flex;align-items:center;gap:5px;margin-right:16px;font-size:14px;cursor:pointer}
button{background:var(--blue);color:#fff;border:none;padding:11px 22px;border-radius:8px;
  font-size:15px;font-weight:600;cursor:pointer}button:hover{background:#163a5a}
button:disabled{background:#a9b2bd;cursor:not-allowed}
button.ghost{background:#fff;color:var(--blue);border:1.5px solid #c4ccd6}
button.ghost:hover{background:#eef2f7}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:4px}
input[type=file]{font-size:13px}
#checkout{margin-top:12px}
.probe{display:flex;align-items:center;gap:8px;font-size:13px;padding:4px 0}
.probe .dot{width:10px;height:10px;border-radius:50%;flex:none}
.dot.ok{background:#28a745}.dot.bad{background:#d6453f}
.banner{border-radius:9px;padding:11px 14px;margin-top:10px;font-size:13.5px}
.banner.good{background:#e8f8ec;border:1px solid #b6e3c2}
.banner.warn{background:#fff4e0;border:1px solid #f0d49a}
.banner.bad{background:#fdecee;border:1px solid #f0bcc0}
.vdesc{font-size:12.5px;color:#566;margin-top:6px;line-height:1.45}
#status{display:none;margin-top:8px;background:#0d1b2a;color:#c8e1ff;border-radius:9px;
  padding:12px 14px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;
  max-height:260px;overflow:auto;white-space:pre-wrap;line-height:1.5}
#summary{display:none;margin-top:14px;gap:10px}
.stat{flex:1;text-align:center;background:#fff;border:1px solid #dde2e8;border-radius:9px;padding:10px}
.stat b{display:block;font-size:24px}.stat.A b{color:var(--green)}.stat.B b{color:#c79100}.stat.C b{color:#b04a52}
#dls{display:none;margin-top:12px;gap:10px}
a.dl{display:inline-block;padding:10px 16px;background:var(--green);color:#fff;text-decoration:none;border-radius:8px;font-weight:600}
a.dl.alt{background:#34507a}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:12.5px;display:none;background:#fff}
th,td{border:1px solid #e3e8ee;padding:5px 7px;text-align:left;vertical-align:top}
th{background:#eef2f7;position:sticky;top:0}
.tierA{background:#e8f8ec}.tierB{background:#fff8e1}.tierC{background:#fdecee}
.tablewrap{max-height:440px;overflow:auto;border-radius:9px;border:1px solid #e3e8ee;margin-top:14px;display:none}
.note{background:#fff8e1;border-left:4px solid #f0c020;padding:9px 13px;border-radius:5px;font-size:12.5px;margin-top:8px}
</style></head><body>
<h1>Lead Engine</h1>
<p class="sub">Scrape, enrich, score &amp; export sales leads — powered by open data (Overture Maps + OpenStreetMap).</p>

<form id="form">
  <fieldset>
    <legend>1 · What to find</legend>
    <label class="fld">Vertical</label>
    <select id="vertical"></select>
    <div class="vdesc" id="vdesc"></div>
  </fieldset>

  <fieldset>
    <legend>2 · Where</legend>
    <div class="row">
      <div>
        <label class="fld">Market</label>
        <input type="text" id="market" list="markets" placeholder="e.g. Austin, Texas  or  sonoma_county_ca">
        <datalist id="markets">{% for m in markets %}<option value="{{m}}">{% endfor %}</datalist>
        <div class="hint">A saved market key, or any place name (we geocode it).</div>
      </div>
      <div>
        <label class="fld">Data sources</label>
        <div class="checks" style="padding-top:8px">
          <label><input type="checkbox" id="src_overture" checked> Overture (bulk, national)</label>
          <label><input type="checkbox" id="src_osm"> OpenStreetMap (live)</label>
        </div>
        <div class="hint">Overture needs the <code>duckdb</code> package; OSM works without it.</div>
      </div>
    </div>
  </fieldset>

  <fieldset id="competitor_box" style="display:none">
    <legend>3 · Skip competitors' clients</legend>
    <label class="fld" id="competitor_label"></label>
    <textarea id="competitor_urls" placeholder="https://a-rival-tc.com/testimonials&#10;https://another-tc.com/clients"></textarea>
    <div class="hint" id="competitor_help"></div>
  </fieldset>

  <fieldset>
    <legend>4 · Skip people already in your CRM <span style="font-weight:400;color:#889">(optional)</span></legend>
    <label class="fld">Upload your current CRM export (.csv)</label>
    <input type="file" id="crm_file" accept=".csv,text/csv">
    <div class="hint" id="crm_status">We match on company name and remove anyone you already have — so you never get a duplicate.</div>
  </fieldset>

  <fieldset>
    <legend>Options</legend>
    <div class="row">
      <div>
        <label class="fld"><input type="checkbox" id="enrich" checked style="width:auto"> Enrich (visit each site)</label>
        <div class="hint">Estimates volume &amp; detects competitor/TC signals. Slower but far richer.</div>
      </div>
      <div>
        <label class="fld">Enrich cap (top N)</label>
        <input type="number" id="enrich_cap" value="150" min="0">
      </div>
      <div>
        <label class="fld">Collect limit (optional)</label>
        <input type="number" id="limit" placeholder="all">
      </div>
    </div>
  </fieldset>

  <div class="btnrow">
    <button type="submit" id="go">Run</button>
    <button type="button" id="demo" class="ghost">▶ Try a demo (no internet needed)</button>
    <button type="button" id="check" class="ghost">📡 Check my connection</button>
  </div>
  <div id="checkout"></div>
</form>

<div id="summary" class="row">
  <div class="stat"><b id="s_total">0</b>total</div>
  <div class="stat A"><b id="s_A">0</b>Tier A</div>
  <div class="stat B"><b id="s_B">0</b>Tier B</div>
  <div class="stat C"><b id="s_C">0</b>Tier C</div>
</div>
<div id="dls" class="row"></div>
<div id="status"></div>
<div class="tablewrap" id="tablewrap"><table id="preview"></table></div>

<script>
const VERTS = {{ verticals|tojson }};
const vsel = document.getElementById("vertical");
VERTS.forEach(v => { const o=document.createElement("option"); o.value=v.key; o.textContent=v.label; vsel.appendChild(o); });

function syncVertical(){
  const v = VERTS.find(x=>x.key===vsel.value);
  document.getElementById("vdesc").textContent = v.description || "";
  const cb = document.getElementById("competitor_box");
  if (v.competitor_input){
    cb.style.display="block";
    document.getElementById("competitor_label").textContent = v.competitor_input.label;
    document.getElementById("competitor_help").textContent = v.competitor_input.help;
  } else cb.style.display="none";
  document.getElementById("src_overture").checked = v.default_sources.includes("overture");
  document.getElementById("src_osm").checked = v.default_sources.includes("osm");
}
vsel.addEventListener("change", syncVertical); syncVertical();

const form=document.getElementById("form"), go=document.getElementById("go");
const demoBtn=document.getElementById("demo"), checkBtn=document.getElementById("check");
const checkout=document.getElementById("checkout");
const statusEl=document.getElementById("status"), summary=document.getElementById("summary");
const dls=document.getElementById("dls"), tablewrap=document.getElementById("tablewrap"), table=document.getElementById("preview");

// Read an uploaded CRM .csv into memory (text) so the server can dedupe against it.
let crmText="";
document.getElementById("crm_file").addEventListener("change", e=>{
  const f=e.target.files[0]; const st=document.getElementById("crm_status");
  if(!f){ crmText=""; return; }
  const reader=new FileReader();
  reader.onload=()=>{ crmText=reader.result||"";
    const lines=crmText.split(/\\r?\\n/).filter(x=>x.trim()).length-1;
    st.textContent=`Loaded ${f.name} — about ${Math.max(0,lines)} companies will be skipped if found.`; };
  reader.readAsText(f);
});

function baseBody(){
  const sources=[]; if(document.getElementById("src_overture").checked) sources.push("overture");
  if(document.getElementById("src_osm").checked) sources.push("osm");
  return {
    vertical:vsel.value, market:document.getElementById("market").value,
    sources, enrich:document.getElementById("enrich").checked,
    enrich_cap:+document.getElementById("enrich_cap").value||0,
    limit:+document.getElementById("limit").value||0,
    competitor_urls:document.getElementById("competitor_urls").value,
    crm_csv:crmText,
  };
}

async function startRun(body){
  go.disabled=true; demoBtn.disabled=true; go.textContent="Running…";
  statusEl.style.display="block"; statusEl.textContent="Starting…"; checkout.innerHTML="";
  summary.style.display="none"; dls.style.display="none"; tablewrap.style.display="none"; table.style.display="none";
  const r=await fetch("/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const j=await r.json();
  if(j.error){ statusEl.textContent="Couldn't start: "+j.error; go.disabled=false; demoBtn.disabled=false; go.textContent="Run"; return; }
  poll(j.job_id);
}

form.addEventListener("submit", e=>{
  e.preventDefault();
  const body=baseBody();
  if(!body.market.trim()){ alert("Enter a market, or click 'Try a demo'."); return; }
  if(!body.sources.length){ alert("Pick at least one data source."); return; }
  body.demo=false; startRun(body);
});

demoBtn.addEventListener("click", ()=>{
  const body=baseBody(); body.demo=true; body.market=body.market||"(demo)";
  startRun(body);
});

checkBtn.addEventListener("click", async ()=>{
  checkBtn.disabled=true; checkout.innerHTML="<div class='hint'>Testing each data source…</div>";
  try{
    const j=await (await fetch("/check")).json();
    let h=j.results.map(p=>`<div class="probe"><span class="dot ${p.ok?'ok':'bad'}"></span>`
      +`<b>${p.label}</b> — ${p.detail}</div>`).join("");
    const cls=(j.can_overture||j.can_osm)?(j.can_overture&&j.can_osm?"good":"warn"):"bad";
    h+=`<div class="banner ${cls}">${j.summary}</div>`;
    checkout.innerHTML=h;
  }catch(e){ checkout.innerHTML="<div class='banner bad'>Could not run the check.</div>"; }
  checkBtn.disabled=false;
});

function poll(jid){
  const t=setInterval(async ()=>{
    const r=await fetch("/progress/"+jid); const j=await r.json();
    statusEl.textContent=j.log.join("\\n"); statusEl.scrollTop=statusEl.scrollHeight;
    if(j.done){
      clearInterval(t); go.disabled=false; demoBtn.disabled=false; go.textContent="Run";
      if(j.error){ checkout.innerHTML=`<div class="banner bad">${j.error}</div>`; }
      if(j.notice){ checkout.innerHTML=`<div class="banner warn">${j.notice}</div>`; }
      if(j.stats){
        summary.style.display="flex";
        s_total.textContent=j.stats.total; s_A.textContent=j.stats.A;
        s_B.textContent=j.stats.B; s_C.textContent=j.stats.C;
      }
      if(j.files && (j.files.csv||j.files.xlsx)){
        dls.style.display="flex"; dls.innerHTML="";
        if(j.files.csv) dls.innerHTML+=`<a class="dl" href="/download/csv/${jid}">⬇ CRM CSV</a>`;
        if(j.files.xlsx) dls.innerHTML+=`<a class="dl alt" href="/download/xlsx/${jid}">⬇ Tiered XLSX</a>`;
      }
      if(j.leads && j.columns) renderTable(j.leads, j.columns);
    }
  }, 700);
}

function renderTable(leads, columns){
  const cols = columns.slice(0, 9); // keep the preview readable
  let h="<thead><tr>"+cols.map(c=>`<th>${c[0]}</th>`).join("")+"</tr></thead><tbody>";
  for(const r of leads){
    const tier=r.tier||"C";
    h+=`<tr class="tier${tier}">`+cols.map(c=>`<td>${(r[c[1]]??"")}</td>`).join("")+"</tr>";
  }
  table.innerHTML=h+"</tbody>"; table.style.display="table"; tablewrap.style.display="block";
}
</script>
</body></html>"""


def main():
    port = free_port()
    print("\n" + "=" * 46)
    print(f"  Lead Engine  →  http://127.0.0.1:{port}")
    print("=" * 46 + "\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
