"use client";

import * as React from "react";
import { ACTIVE_CASE_CHANGED_EVENT } from "@/lib/api";

/**
 * How many times the active case has changed since this component mounted.
 *
 * Switching cases has to switch the data under every workspace screen, and
 * the screens fetch their own data on mount. The (app) layout therefore keys
 * its page wrapper on this number: each change throws the old page away and
 * mounts the next one against the new selection — the same thing a
 * navigation between screens does. The header, which sits outside that
 * wrapper, uses it to re-read the selection.
 */
export function useActiveCaseVersion(): number {
  const [version, setVersion] = React.useState(0);
  React.useEffect(() => {
    const onChanged = () => setVersion((current) => current + 1);
    window.addEventListener(ACTIVE_CASE_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(ACTIVE_CASE_CHANGED_EVENT, onChanged);
  }, []);
  return version;
}
