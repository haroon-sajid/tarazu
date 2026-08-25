import { redirect } from "next/navigation";

/** /settings opens on the first panel. */
export default function SettingsIndex() {
  redirect("/settings/general");
}
