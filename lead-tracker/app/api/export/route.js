import { exportLeads } from "../../../lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FIELDS = [
  "name", "category", "city", "address", "phone", "website", "email",
  "tier", "tier_reason", "status", "notes", "last_contacted", "favorite",
  "lat", "lon", "id",
];

function csvCell(v) {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function GET(request) {
  const sp = new URL(request.url).searchParams;
  const p = Object.fromEntries(sp.entries());
  const rows = exportLeads(p);

  const lines = [FIELDS.join(",")];
  for (const r of rows) lines.push(FIELDS.map((f) => csvCell(r[f])).join(","));
  const csv = lines.join("\n");

  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="leads-${stamp}.csv"`,
    },
  });
}
