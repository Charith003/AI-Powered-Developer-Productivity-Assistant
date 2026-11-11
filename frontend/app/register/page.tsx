"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, AuthResult } from "../../lib/api";
export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api<AuthResult>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ email: form.get("email"), full_name: form.get("full_name"), password: form.get("password") }) });
      router.replace("/dashboard");
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to create account"); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-screen place-items-center px-5 py-12"><div className="w-full max-w-md rounded-3xl border border-[#E7EDE2] bg-white p-8 shadow-sm"><Link href="/" className="font-bold">DevPilot AI</Link><h1 className="mt-8 text-3xl font-semibold">Create your account</h1><p className="mt-2 text-sm text-[#748174]">Start organizing your engineering work.</p><form onSubmit={submit} className="mt-7 space-y-4"><label className="block text-sm font-medium">Full name<input name="full_name" required minLength={1} maxLength={120} autoComplete="name" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 outline-none focus:border-[#8cbd44]" /></label><label className="block text-sm font-medium">Email<input name="email" type="email" required autoComplete="email" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 outline-none focus:border-[#8cbd44]" /></label><label className="block text-sm font-medium">Password<input name="password" type="password" required minLength={12} maxLength={128} autoComplete="new-password" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 outline-none focus:border-[#8cbd44]" /><span className="mt-1 block text-xs font-normal text-[#748174]">Use at least 12 characters.</span></label>{error && <p role="alert" className="text-sm text-red-700">{error}</p>}<button disabled={busy} className="w-full rounded-xl bg-[#B7F34A] px-4 py-3 font-semibold disabled:opacity-60">{busy ? "Creating account…" : "Create account"}</button></form><p className="mt-6 text-sm text-[#748174]">Already registered? <Link className="font-semibold text-ink" href="/login">Sign in</Link></p></div></main>;
}
