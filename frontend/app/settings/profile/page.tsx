"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Profile } from "../../../lib/api";
export default function ProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { void api<Profile>("/api/v1/auth/me").then(setProfile).catch(() => router.replace("/login")); }, [router]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setMessage(""); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const updated = await api<Profile>("/api/v1/auth/me", { method: "PATCH", body: JSON.stringify({ full_name: form.get("full_name") }) });
      setProfile(updated); setMessage("Profile saved.");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to update profile"); }
  }
  return <main className="min-h-screen"><header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-4"><Link href="/" className="font-bold">DevPilot AI</Link><nav className="flex gap-4 text-sm font-medium"><Link href="/settings/ai">AI settings</Link><Link href="/dashboard">Back to projects</Link></nav></div></header><section className="mx-auto max-w-2xl px-5 py-10"><p className="text-sm text-[#748174]">Settings</p><h1 className="mt-1 text-3xl font-semibold">Profile</h1><p className="mt-2 text-[#748174]">Manage the name shown in your workspace.</p><form onSubmit={save} className="mt-7 rounded-2xl border border-[#E7EDE2] bg-white p-6"><label className="block text-sm font-medium">Full name<input name="full_name" required minLength={1} maxLength={120} defaultValue={profile?.full_name ?? ""} key={profile?.full_name} className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5" /></label><label className="mt-4 block text-sm font-medium">Email<input value={profile?.email ?? ""} readOnly className="mt-1.5 w-full rounded-xl border border-[#e7ede2] bg-[#f7f9f4] px-3 py-2.5 text-[#748174]" /></label>{message && <p role="status" className="mt-4 text-sm text-green-700">{message}</p>}{error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}<button className="mt-5 rounded-xl bg-[#B7F34A] px-4 py-2.5 font-semibold">Save changes</button></form></section></main>;
}

