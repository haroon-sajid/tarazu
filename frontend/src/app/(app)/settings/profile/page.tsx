"use client";

/**
 * Settings → Profile. The one place a person edits how they appear: picture,
 * display name, job title, phone. Live against GET/PUT /v1/profile — the
 * contract is a full replacement, so this form always submits every field.
 *
 * The picture never touches a file store: it is downscaled in the browser to
 * a small square JPEG and sent as a data: URL, which the backend size-caps.
 */

import * as React from "react";
import { Check, Loader2, Trash2, Upload } from "lucide-react";
import { ApiError, getProfile, saveProfile } from "@/lib/api";
import type { UserProfile } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { SectionHeader, SettingRow, Toggle } from "../_components/shared";

/** Fired after a save so the header and sidebar avatars refresh (the
 * ProfileMenu listens for the same name). */
const PROFILE_UPDATED_EVENT = "tarazu:profile-updated";

const AVATAR_SIZE = 256;

/** Downscale to a small square JPEG data URL, well inside the API's cap. */
async function fileToAvatar(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error("unreadable image"));
      element.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = AVATAR_SIZE;
    canvas.height = AVATAR_SIZE;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas unavailable");
    // Cover-crop the shorter side so faces stay centred, not squashed.
    const side = Math.min(image.width, image.height);
    context.drawImage(
      image,
      (image.width - side) / 2,
      (image.height - side) / 2,
      side,
      side,
      0,
      0,
      AVATAR_SIZE,
      AVATAR_SIZE,
    );
    return canvas.toDataURL("image/jpeg", 0.85);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function ProfileSettingsPage() {
  const { session } = useAuth();
  const [profile, setProfile] = React.useState<UserProfile | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const [fullName, setFullName] = React.useState("");
  const [jobTitle, setJobTitle] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [avatar, setAvatar] = React.useState<string | null>(null);
  const [gender, setGender] = React.useState("");
  const [dateOfBirth, setDateOfBirth] = React.useState("");
  const [location, setLocation] = React.useState("");
  const [licenseNumber, setLicenseNumber] = React.useState("");
  const [language, setLanguage] = React.useState("");
  const [notifyCaseReady, setNotifyCaseReady] = React.useState(true);
  const [notifyHighSeverity, setNotifyHighSeverity] = React.useState(true);
  const [notifyWeeklyDigest, setNotifyWeeklyDigest] = React.useState(false);

  const [busy, setBusy] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(() => {
    setLoadError(null);
    setProfile(null);
    getProfile()
      .then((loaded) => {
        setProfile(loaded);
        setFullName(loaded.full_name ?? "");
        setJobTitle(loaded.job_title ?? "");
        setPhone(loaded.phone ?? "");
        setAvatar(loaded.avatar);
        // Keep a lightweight local copy so the picture survives refreshes even
        // if the backend GET is momentarily empty. Removed avatars clear it.
        try {
          const cached = window.localStorage.getItem("tarazu.profile-avatar-cache");
          if (loaded.avatar) {
            window.localStorage.setItem("tarazu.profile-avatar-cache", loaded.avatar);
          } else if (cached) {
            setAvatar(cached);
          }
        } catch {
          // Storage may be unavailable; the API copy is the source of truth.
        }
        setGender(loaded.gender ?? "");
        setDateOfBirth(loaded.date_of_birth ?? "");
        setLocation(loaded.location ?? "");
        setLicenseNumber(loaded.license_number ?? "");
        setLanguage(loaded.language ?? "");
        setNotifyCaseReady(loaded.notify_case_ready);
        setNotifyHighSeverity(loaded.notify_high_severity);
        setNotifyWeeklyDigest(loaded.notify_weekly_digest);
      })
      .catch((caught) =>
        setLoadError(
          caught instanceof ApiError ? caught.message : "Could not load your profile.",
        ),
      );
  }, []);

  React.useEffect(load, [load]);

  const persist = React.useCallback(
    async (avatarValue: string | null) => {
      if (busy) return;
      setBusy(true);
      setSaveError(null);
      setSaved(false);
      try {
        const stored = await saveProfile({
          full_name: fullName,
          job_title: jobTitle,
          phone,
          avatar: avatarValue,
          gender,
          date_of_birth: dateOfBirth || null,
          location,
          license_number: licenseNumber,
          language: language || null,
          notify_case_ready: notifyCaseReady,
          notify_high_severity: notifyHighSeverity,
          notify_weekly_digest: notifyWeeklyDigest,
        });
        setProfile(stored);
        setAvatar(stored.avatar);
        setSaved(true);
        window.dispatchEvent(new Event(PROFILE_UPDATED_EVENT));
        window.setTimeout(() => setSaved(false), 2500);
        try {
          window.localStorage.setItem(
            "tarazu.profile-avatar-cache",
            stored.avatar ?? "",
          );
        } catch {
          // Ignore storage failures.
        }
      } catch (caught) {
        setSaveError(
          caught instanceof ApiError ? caught.message : "Could not save your profile.",
        );
      } finally {
        setBusy(false);
      }
    },
    [
      busy,
      fullName,
      jobTitle,
      phone,
      gender,
      dateOfBirth,
      location,
      licenseNumber,
      language,
      notifyCaseReady,
      notifyHighSeverity,
      notifyWeeklyDigest,
    ],
  );

  const pickFile = async (file: File | undefined) => {
    if (!file) return;
    setSaveError(null);
    if (!file.type.startsWith("image/")) {
      setSaveError("The profile picture must be an image file.");
      return;
    }
    try {
      const dataUrl = await fileToAvatar(file);
      setAvatar(dataUrl);
      await persist(dataUrl);
    } catch {
      setSaveError("That image could not be read. Try a different file.");
    }
  };

  const submit = () => persist(avatar);

  const initial = (session?.email[0] ?? "A").toUpperCase();

  return (
    <div>
      <SectionHeader
        title="Profile"
        description="How you appear across Tarazu."
      />

      {loadError ? (
        <ErrorState message={loadError} onRetry={load} />
      ) : profile === null ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <div className="space-y-8">
          {/* Picture */}
          <div className="flex items-center gap-5">
            {avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={avatar}
                alt="Your profile picture"
                className="h-20 w-20 rounded-full object-cover ring-1 ring-slate-200"
              />
            ) : (
              <span className="flex h-20 w-20 items-center justify-center rounded-full bg-brand-800 text-3xl font-bold text-white">
                {initial}
              </span>
            )}
            <div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => fileRef.current?.click()}
                >
                  {busy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Upload className="h-3.5 w-3.5" aria-hidden />
                  )}
                  {avatar ? "Change photo" : "Upload photo"}
                </Button>
                {avatar && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => persist(null)}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                    Remove
                  </Button>
                )}
              </div>
              <p className="mt-1.5 text-xs text-ink-400">
                Any image works: it is cropped square and resized in your
                browser before upload.
              </p>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => {
                  void pickFile(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </div>
          </div>

          {/* Two balanced columns so the panel uses its full width; the save
              row closes the shorter left column so neither side trails off. */}
          <div className="grid gap-x-12 gap-y-8 lg:grid-cols-2">
          <div className="space-y-8">
          {/* Identity */}
          <section className="space-y-4">
            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Identity
            </h3>
            <Input
              label="Full name"
              value={fullName}
              maxLength={100}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Haroon Sajid"
              hint="Shown in the sidebar and the member list."
            />
            <Input
              label="Email"
              value={session?.email ?? ""}
              disabled
              hint="Your sign-in identity."
            />
          </section>

          {/* Personal */}
          <section className="space-y-4">
            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Personal
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <Select
                label="Gender"
                value={gender}
                onChange={(event) => setGender(event.target.value)}
              >
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </Select>
              <Input
                label="Date of birth"
                type="date"
                value={dateOfBirth}
                onChange={(event) => setDateOfBirth(event.target.value)}
              />
              <Input
                label="Location"
                value={location}
                maxLength={100}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Lahore"
              />
              <Input
                label="Phone"
                value={phone}
                maxLength={40}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="+92 300 1234567"
              />
            </div>
          </section>

          {saveError && (
            <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
              {saveError}
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button onClick={submit} disabled={busy}>
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : saved ? (
                <Check className="h-4 w-4" aria-hidden />
              ) : null}
              {saved ? "Saved" : "Save profile"}
            </Button>
            <p className="text-xs text-ink-400">A save replaces the whole profile.</p>
          </div>
          </div>

          <div className="space-y-8">
          {/* Professional */}
          <section className="space-y-4">
            <h3 className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Professional
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Job title"
                value={jobTitle}
                maxLength={100}
                onChange={(event) => setJobTitle(event.target.value)}
                placeholder="Audit Partner"
              />
              <Input
                label="License / membership no."
                value={licenseNumber}
                maxLength={60}
                onChange={(event) => setLicenseNumber(event.target.value)}
                placeholder="ICAP-12345"
              />
            </div>
          </section>

          {/* Preferences */}
          <section>
            <h3 className="mb-4 text-[10px] font-semibold uppercase tracking-wide text-ink-400">
              Preferences
            </h3>
            <Select
              label="Language for explanations"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              hint="The assistant follows this preference."
            >
              <option value="">No preference</option>
              <option value="en">English</option>
              <option value="ur">اردو (Urdu)</option>
            </Select>
            <div className="mt-2 divide-y divide-slate-100">
              <SettingRow
                name="Case ready for review"
                description="Extraction and matching finished and the review queue is populated"
                action={
                  <Toggle
                    checked={notifyCaseReady}
                    onChange={setNotifyCaseReady}
                    label="Notify when a case is ready for review"
                  />
                }
              />
              <SettingRow
                name="High-severity flag raised"
                description="A rule flagged an item with high severity"
                action={
                  <Toggle
                    checked={notifyHighSeverity}
                    onChange={setNotifyHighSeverity}
                    label="Notify on high-severity flags"
                  />
                }
              />
              <SettingRow
                name="Weekly summary"
                description="Open items, decisions made, and outstanding flags for the week"
                action={
                  <Toggle
                    checked={notifyWeeklyDigest}
                    onChange={setNotifyWeeklyDigest}
                    label="Send a weekly summary"
                  />
                }
              />
            </div>
            <p className="text-[11px] text-ink-400">
              Saved now; email delivery activates when it ships.
            </p>
          </section>
          </div>
          </div>
        </div>
      )}
    </div>
  );
}
