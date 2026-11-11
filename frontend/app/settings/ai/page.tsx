"use client";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../lib/api";

type AIStatus = { provider: string; model: string; embedding_model: string; api_key_configured: boolean; available: boolean; message: string | null };
type UsageSummary = { requests: number; successful_requests: number; failed_requests: number; input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost_usd: string | null };
type UsageItem = { id: string; provider: string; model: string; feature: string; input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost_usd: string | null; status: string; duration_ms: number; created_at: string };
type AIAnswer = { answer: string; key_points: string[] };

function cost(value: string | null) {
  return value === null ? "Not priced" : "$" + Number(value).toFixed(6);
}

export default function AISettingsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [history, setHistory] = useState<UsageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [answer, setAnswer] = useState<AIAnswer | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const providerStatus = await api<AIStatus>("/api/v1/ai/status");
      setStatus(providerStatus);
      const usageSummary = await api<UsageSummary>("/api/v1/ai/usage/summary");
      setSummary(usageSummary);
      const usage = await api<UsageItem[]>("/api/v1/ai/usage?limit=20");
      setHistory(usage);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unable to load AI settings.";
      if (message.includes("401") || message.toLowerCase().includes("token")) router.replace("/login");
      else setError(message);
    } finally { setLoading(false); }
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setAnswer(null);
    const form = new FormData(event.currentTarget);
    try {
      const result = await api<AIAnswer>("/api/v1/ai/generate", {
        method: "POST",
        body: JSON.stringify({ prompt: form.get("prompt") }),
      });
      setAnswer(result);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "AI request failed."); }
    finally { setBusy(false); }
  }

  return <main className="min-h-screen"><header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><Link href="/" className="font-bold">DevPilot AI</Link><nav className="flex items-center gap-4 text-sm"><Link href="/dashboard" className="font-medium">Projects</Link><Link href="/settings/profile" className="font-medium">Profile</Link></nav></div></header><div className="mx-auto max-w-6xl px-5 py-10"><p className="text-sm text-[#748174]">Settings</p><h1 className="mt-1 text-3xl font-semibold">AI provider</h1><p className="mt-2 text-[#748174]">Provider readiness and usage are read from your backend configuration and persisted requests.</p>
    {error && <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
    {loading ? <p className="mt-8 text-sm text-[#748174]">Loading provider settings…</p> : <>
      {status && <section className={"mt-7 rounded-2xl border p-5 " + (status.available ? "border-[#cfe4b5] bg-[#f7fbed]" : "border-[#ead8bb] bg-[#fffaf0]")}><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-[#748174]">Provider status</p><h2 className="mt-1 text-xl font-semibold">{status.provider} · {status.available ? "Available" : "Not configured"}</h2></div><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold">{status.api_key_configured ? "Backend key detected" : "Backend key missing"}</span></div><p className="mt-3 text-sm text-[#566352]">Model: <span className="font-medium">{status.model}</span> · Embedding model setting: <span className="font-medium">{status.embedding_model}</span></p>{status.message && <p className="mt-3 text-sm text-[#765928]">{status.message}</p>}</section>}
      <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
        ["Requests", summary?.requests ?? 0], ["Input tokens", summary?.input_tokens ?? 0], ["Output tokens", summary?.output_tokens ?? 0], ["Estimated cost", cost(summary?.estimated_cost_usd ?? null)],
      ].map(([label, value]) => <article key={String(label)} className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><p className="text-sm text-[#748174]">{label}</p><p className="mt-2 text-2xl font-semibold">{typeof value === "number" ? value.toLocaleString() : value}</p></article>)}</section>
      <section className="mt-7 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]"><form onSubmit={generate} className="h-fit rounded-2xl border border-[#E7EDE2] bg-white p-5"><h2 className="font-semibold">Try the AI assistant</h2><p className="mt-1 text-sm text-[#748174]">Prompts are sent to the configured provider and are not stored in usage records.</p><label className="mt-4 block text-sm font-medium">Engineering question<textarea name="prompt" required minLength={1} maxLength={20000} rows={5} className="mt-1.5 w-full resize-y rounded-xl border border-[#dfe7d8] px-3 py-2.5" placeholder="Ask a question about an engineering task…" /></label><button disabled={!status?.available || busy} className="mt-4 rounded-xl bg-[#B7F34A] px-4 py-2.5 font-semibold disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Asking…" : "Ask assistant"}</button></form><div className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex items-baseline justify-between"><h2 className="font-semibold">Recent usage</h2><span className="text-xs text-[#748174]">{history.length} shown</span></div>{history.length === 0 ? <div className="mt-4 rounded-xl border border-dashed border-[#d6dfcf] px-5 py-10 text-center"><p className="font-medium">No AI requests yet</p><p className="mt-1 text-sm text-[#748174]">Usage will appear here after an AI request.</p></div> : <ul className="mt-4 divide-y divide-[#edf1e9]">{history.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><div><p className="font-medium">{item.feature.replaceAll("_", " ")} · {item.status.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-[#748174]">{item.model} · {item.total_tokens.toLocaleString()} tokens · {new Date(item.created_at).toLocaleString()}</p></div><span className="text-xs text-[#748174]">{cost(item.estimated_cost_usd)}</span></li>)}</ul>}</div></section>
      {answer && <section className="mt-6 rounded-2xl border border-[#cfe4b5] bg-white p-5"><h2 className="font-semibold">Assistant response</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-7">{answer.answer}</p>{answer.key_points.length > 0 && <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[#566352]">{answer.key_points.map((point, index) => <li key={String(index) + point}>{point}</li>)}</ul>}</section>}
    </>}</div></main>;
}
