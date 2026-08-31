"use client";

import * as React from "react";
import { useActiveCaseVersion } from "@/lib/use-active-case";

/**
 * The page wrapper that remounts when the active case changes.
 *
 * Every screen in this group — dashboard, documents, review, assistant, audit
 * trail, reports — is about one case and reads the browser's saved selection
 * when it fetches. Keying this element on the active-case version makes a
 * case switch a data switch: the old page unmounts, the new one mounts, and
 * every screen refetches for whatever the header (or the Cases screen) just
 * selected. The header and sidebar sit outside it and stay mounted, so the
 * switch itself never flickers.
 */
export function Workspace({ children }: { children: React.ReactNode }) {
  const version = useActiveCaseVersion();
  return <div key={version}>{children}</div>;
}
