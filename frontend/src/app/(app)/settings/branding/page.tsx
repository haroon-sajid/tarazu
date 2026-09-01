"use client";

/**
 * Settings → Report branding: the firm's letterhead.
 *
 * A report is the deliverable a client actually receives, and it goes out under
 * the firm's name, not Tarazu's. This panel is where that identity is set: the
 * legal name, the registration number under it, how to reach the firm, and the
 * mark printed at the top of every page.
 *
 * Presentation only. Nothing on this screen is an authorization input, and
 * nothing here changes a number, a match, or a decision — it changes what the
 * finished PDF looks like. A firm that fills nothing in still gets its
 * organization name and the plain layout.
 *
 * Two things the UI has to be honest about:
 *
 *  - **A save is a full replacement.** The contract sends every field on each
 *    save, so a box left empty is a box cleared. The form says so where the
 *    button is, not in a tooltip.
 *  - **Only an owner may save.** The letterhead a client receives is the firm's
 *    identity rather than one auditor's preference, so the backend answers 403
 *    to a member. That is explained here in words rather than surfaced raw.
 *
 * The logo never touches a file store: it is read in the browser as a
 * `data:image/...;base64,...` URL, exactly like a user's avatar, and checked
 * against the API's cap *before* it is sent so an oversized file gets a useful
 * sentence instead of a 422.
 */

import * as React from "react";
import { Building2, Check, Loader2, Trash2, Upload } from "lucide-react";
import { ApiError, getOrgProfile, updateOrgProfile } from "@/lib/api";
import type { OrgProfileResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { formatFileSize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { SectionHeader, SettingsSection } from "../_components/shared";

/** `MAX_LOGO_CHARS` in `backend/app/shared/api.py`: ~300 KB of image. */
const LOGO_MAX_CHARS = 400_000;

/** The formats the API's own validator accepts, and nothing else. */
const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const LOGO_DATA_URL = /^data:image\/(png|jpeg|jpg|webp);base64,/;

const textareaClass =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900 " +
  "placeholder:text-ink-400 focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600";

/** Read the file as it is — a logo keeps its own format and transparency. */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("unreadable image"));
    };
    reader.onerror = () => reject(new Error("unreadable image"));
    reader.readAsDataURL(file);
  });
}

export default function BrandingSettingsPage() {
  const { session } = useAuth();
  const [profile, setProfile] = React.useState<OrgProfileResponse | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [legalName, setLegalName] = React.useState("");
  const [address, setAddress] = React.useState("");
  const [contactEmail, setContactEmail] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [registrationNumber, setRegistrationNumber] = React.useState("");
  const [reportFooter, setReportFooter] = React.useState("");
  const [logo, setLogo] = React.useState<string | null>(null);

  const [busy, setBusy] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setProfile(null);
    getOrgProfile()
      .then((loaded) => {
        setProfile(loaded);
        setLegalName(loaded.legal_name ?? "");
        setAddress(loaded.address ?? "");
        setContactEmail(loaded.contact_email ?? "");
        setPhone(loaded.phone ?? "");
        setWebsite(loaded.website ?? "");
        setRegistrationNumber(loaded.registration_number ?? "");
        setReportFooter(loaded.report_footer ?? "");
        setLogo(loaded.logo);
      })
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "Could not load the firm's branding.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  /**
   * Validate before sending, not after. The backend caps the data URL at
   * 400,000 characters and rejects anything that is not a PNG, JPEG, or WebP;
   * both checks happen here so the auditor gets a sentence they can act on
   * instead of a 422 from the API.
   */
  const pickLogo = async (file: File | undefined) => {
    if (!file) return;
    setSaveError(null);
    setSaved(false);
    if (!LOGO_TYPES.includes(file.type)) {
      setSaveError(
        "The logo must be a PNG, JPEG, or WebP image. PNG is usually the right " +
          "choice for a letterhead mark, because it keeps a transparent background.",
      );
      return;
    }
    let dataUrl: string;
    try {
      dataUrl = await fileToDataUrl(file);
    } catch {
      setSaveError("That image could not be read. Try a different file.");
      return;
    }
    if (!LOGO_DATA_URL.test(dataUrl)) {
      setSaveError(
        "That file did not read back as a PNG, JPEG, or WebP image. Try " +
          "exporting it again from your design tool.",
      );
      return;
    }
    if (dataUrl.length > LOGO_MAX_CHARS) {
      setSaveError(
        `That logo is too large. ${formatFileSize(file.size)} encodes to ` +
          `${dataUrl.length.toLocaleString()} characters and the limit is ` +
          `${LOGO_MAX_CHARS.toLocaleString()} (roughly 300 KB of image). Export it ` +
          "smaller (a letterhead mark rarely needs to be wider than about 600 " +
          "pixels) and upload it again.",
      );
      return;
    }
    setLogo(dataUrl);
  };

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setSaveError(null);
    setSaved(false);
    try {
      // Full replacement: every field goes on every save, so an empty box
      // clears the stored value rather than leaving it behind.
      const stored = await updateOrgProfile({
        legal_name: legalName,
        address,
        contact_email: contactEmail,
        phone,
        website,
        registration_number: registrationNumber,
        logo: logo ?? null,
        report_footer: reportFooter,
      });
      setProfile(stored);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) {
        setSaveError(
          "Only an owner can change the firm's report branding. You can read " +
            "the letterhead your reports carry, but changing what the firm " +
            "presents to its clients is an owner's act. Ask an owner of your " +
            "organization to make the change.",
        );
      } else if (caught instanceof ApiError && caught.status === 501) {
        setSaveError(
          "Saving the letterhead needs the live backend. Set " +
            "NEXT_PUBLIC_TARAZU_API_URL and sign in, then try again.",
        );
      } else if (caught instanceof ApiError && caught.status === 422) {
        setSaveError(
          `The backend rejected the branding: ${caught.message}`,
        );
      } else {
        setSaveError(
          caught instanceof ApiError
            ? caught.message
            : "Could not save the firm's branding.",
        );
      }
    } finally {
      setBusy(false);
    }
  };

  // The role is only known when this browser has the org claim from signup or
  // an invitation; unknown is not "not an owner", so the notice stays quiet and
  // the save's own 403 does the explaining.
  const knownNonOwner = session?.role != null && session.role !== "owner";

  const displayName = legalName.trim() || profile?.name || "Your firm";
  const contactLine = [contactEmail.trim(), phone.trim(), website.trim()]
    .filter(Boolean)
    .join("  ·  ");

  return (
    <div>
      <SectionHeader
        title="Report branding"
        description="Your firm's letterhead: what a client sees at the top of every report Tarazu generates for you. Presentation only: nothing here changes a number, a match, or a decision."
      />

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : profile === null ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : (
        <>
          {knownNonOwner && (
            <p className="mb-6 rounded-md bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 ring-1 ring-amber-300">
              You are signed in as a {session?.role}. The letterhead is the
              firm's identity rather than one auditor's preference, so only an
              owner can save changes here. You can see what your reports carry,
              and an owner can change it.
            </p>
          )}

          <div className="grid gap-x-12 gap-y-8 lg:grid-cols-2">
            {/* The form */}
            <div>
              <SettingsSection
                title="Logo"
                description="Printed at the top of every report page. PNG, JPEG, or WebP, up to about 300 KB. A PNG with a transparent background usually looks best."
              >
                <div className="flex flex-wrap items-center gap-5 py-4">
                  {logo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={logo}
                      alt="Your firm's logo"
                      className="h-16 w-auto max-w-[12rem] object-contain"
                    />
                  ) : (
                    <span className="flex h-16 w-16 items-center justify-center rounded-lg bg-slate-100 text-ink-400 ring-1 ring-slate-200">
                      <Building2 className="h-7 w-7" aria-hidden />
                    </span>
                  )}
                  <div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => fileRef.current?.click()}
                      >
                        <Upload className="h-3.5 w-3.5" aria-hidden />
                        {logo ? "Change logo" : "Upload logo"}
                      </Button>
                      {logo && (
                        <Button size="sm" variant="outline" onClick={() => setLogo(null)}>
                          <Trash2 className="h-3.5 w-3.5" aria-hidden />
                          Remove
                        </Button>
                      )}
                    </div>
                    <p className="mt-1.5 text-xs text-ink-400">
                      The image is read in your browser and stored inline with
                      the branding. There is no separate file store, and the
                      size is checked here before anything is sent.
                    </p>
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(event) => {
                        void pickLogo(event.target.files?.[0]);
                        event.target.value = "";
                      }}
                    />
                  </div>
                </div>
              </SettingsSection>

              <SettingsSection
                title="Firm details"
                description="Printed under the logo. Leave anything out that you do not want on the page."
              >
                <div className="space-y-4 py-4">
                  <Input
                    label="Legal name"
                    value={legalName}
                    maxLength={200}
                    onChange={(event) => setLegalName(event.target.value)}
                    placeholder={profile.name}
                    hint={`The name the report is issued under. Left empty, reports use “${profile.name}”.`}
                  />
                  <Input
                    label="Registration number"
                    value={registrationNumber}
                    maxLength={80}
                    onChange={(event) => setRegistrationNumber(event.target.value)}
                    placeholder="ICAP firm reg. 0123"
                    hint="Practising licence or institute registration, printed under the firm name."
                  />
                  <div>
                    <label
                      htmlFor="branding-address"
                      className="mb-1 block text-xs font-medium text-ink-600"
                    >
                      Address
                    </label>
                    <textarea
                      id="branding-address"
                      rows={3}
                      maxLength={400}
                      value={address}
                      onChange={(event) => setAddress(event.target.value)}
                      placeholder={"12 Ferozepur Road\nGulberg III, Lahore 54660"}
                      className={textareaClass}
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Input
                      label="Contact email"
                      type="email"
                      value={contactEmail}
                      maxLength={200}
                      onChange={(event) => setContactEmail(event.target.value)}
                      placeholder="audit@yourfirm.pk"
                    />
                    <Input
                      label="Phone"
                      value={phone}
                      maxLength={40}
                      onChange={(event) => setPhone(event.target.value)}
                      placeholder="+92 42 3577 0000"
                    />
                  </div>
                  <Input
                    label="Website"
                    value={website}
                    maxLength={200}
                    onChange={(event) => setWebsite(event.target.value)}
                    placeholder="yourfirm.pk"
                  />
                </div>
              </SettingsSection>

              <SettingsSection
                title="Report footer"
                description="One line printed at the foot of every report page. A confidentiality note or an engagement reference usually lives here."
              >
                <div className="py-4">
                  <textarea
                    id="branding-footer"
                    rows={2}
                    maxLength={300}
                    value={reportFooter}
                    onChange={(event) => setReportFooter(event.target.value)}
                    placeholder="Confidential. Prepared for the addressee only."
                    className={textareaClass}
                    aria-label="Report footer"
                  />
                  <p className="mt-1 text-[11px] text-ink-400">
                    {reportFooter.length} of 300 characters.
                  </p>
                </div>
              </SettingsSection>

              {saveError && (
                <p className="mb-3 rounded-md bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-700 ring-1 ring-rose-200">
                  {saveError}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={submit} disabled={busy}>
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                  ) : saved ? (
                    <Check className="h-4 w-4" aria-hidden />
                  ) : null}
                  {saved ? "Saved" : "Save branding"}
                </Button>
                <p className="max-w-sm text-xs text-ink-400">
                  A save replaces the whole letterhead: every field above is
                  sent, so anything you clear here is cleared on the reports too.
                </p>
              </div>
              {profile.updated_at && (
                <p className="mt-2 text-[11px] text-ink-400">
                  Last saved {new Date(profile.updated_at).toLocaleString("en-GB")}.
                </p>
              )}
            </div>

            {/* Live preview of the page head a client receives */}
            <div>
              <SettingsSection
                title="Preview"
                description="How the top of a generated report reads with these details. Existing reports are immutable and keep the letterhead they were generated with."
              >
                <div className="py-4">
                  <div className="mx-auto max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-300 pb-4">
                      <div className="min-w-0">
                        {logo ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={logo}
                            alt=""
                            className="mb-2 h-10 w-auto max-w-[10rem] object-contain"
                          />
                        ) : null}
                        <p className="break-words text-base font-bold text-ink-900">
                          {displayName}
                        </p>
                        {registrationNumber.trim() && (
                          <p className="mt-0.5 text-[11px] text-ink-600">
                            {registrationNumber.trim()}
                          </p>
                        )}
                      </div>
                      <div className="min-w-0 text-right text-[11px] leading-relaxed text-ink-600">
                        {address.trim() && (
                          <p className="whitespace-pre-wrap break-words">
                            {address.trim()}
                          </p>
                        )}
                        {contactLine && (
                          <p className="mt-1 break-words">{contactLine}</p>
                        )}
                      </div>
                    </div>

                    <p className="mt-5 text-sm font-semibold text-ink-900">
                      Reconciliation report
                    </p>
                    <p className="mt-0.5 text-[11px] text-ink-400">
                      Client, period, and every decided item follow here, with
                      provenance and the audit trail.
                    </p>
                    <div className="mt-4 space-y-1.5" aria-hidden>
                      <div className="h-1.5 w-full rounded-full bg-slate-100" />
                      <div className="h-1.5 w-11/12 rounded-full bg-slate-100" />
                      <div className="h-1.5 w-9/12 rounded-full bg-slate-100" />
                    </div>

                    <p className="mt-6 border-t border-slate-200 pt-3 text-[10px] leading-relaxed text-ink-400">
                      {reportFooter.trim() ||
                        "No footer set. Reports print without one."}
                    </p>
                  </div>
                  <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
                    A sketch of the page head, not the report itself. Generate a
                    report from the Reports screen to see the real document.
                  </p>
                </div>
              </SettingsSection>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
