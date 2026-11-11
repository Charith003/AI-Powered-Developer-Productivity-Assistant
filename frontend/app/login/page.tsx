"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, AuthResult } from "../../lib/api";
export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api<AuthResult>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email: form.get("email"), password: form.get("password") }) });
      router.replace("/dashboard");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in"); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-screen place-items-center px-5 py-12"><div className="w-full max-w-md rounded-3xl border border-[#E7EDE2] bg-white p-8 shadow-sm"><Link href="/" className="font-bold">DevPilot AI</Link><h1 className="mt-8 text-3xl font-semibold">Welcome back</h1><p className="mt-2 text-sm text-[#748174]">Sign in to continue to your engineering workspace.</p><form onSubmit={submit} className="mt-7 space-y-4"><label className="block text-sm font-medium">Email<input name="email" type="email" required autoComplete="email" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 outline-none focus:border-[#8cbd44]" /></label><label className="block text-sm font-medium">Password<input name="password" type="password" required autoComplete="current-password" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 outline-none focus:border-[#8cbd44]" /></label>{error && <p role="alert" className="text-sm text-red-700">{error}</p>}<button disabled={busy} className="w-full rounded-xl bg-[#B7F34A] px-4 py-3 font-semibold disabled:opacity-60">{busy ? "Signing in…" : "Sign in"}</button></form><p className="mt-6 text-sm text-[#748174]">New to DevPilot? <Link className="font-semibold text-ink" href="/register">Create an account</Link></p></div></main>;
}
