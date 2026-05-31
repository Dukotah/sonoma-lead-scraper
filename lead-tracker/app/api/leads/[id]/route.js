import { updateCrm } from "../../../../lib/db";

export const runtime = "nodejs";

export async function PATCH(request, { params }) {
  const { id } = await params;
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const next = updateCrm(id, body || {});
  if (!next) return Response.json({ error: "lead not found" }, { status: 404 });
  return Response.json(next);
}
