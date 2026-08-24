import { redirect } from "next/navigation";

/** The demo starts at the upload screen. */
export default function Home() {
  redirect("/upload");
}
