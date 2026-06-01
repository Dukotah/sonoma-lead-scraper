import { redirect } from "next/navigation";

// Standalone convenience: the tracker lives at /leads. When you drop these files
// into your own Next.js app you can delete this and just keep app/leads/.
export default function Home() {
  redirect("/leads");
}
