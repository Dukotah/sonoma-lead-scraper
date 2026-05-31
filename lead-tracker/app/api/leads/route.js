import { queryLeads } from "../../../lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request) {
  const sp = new URL(request.url).searchParams;
  const p = Object.fromEntries(sp.entries());
  return Response.json(queryLeads(p));
}
