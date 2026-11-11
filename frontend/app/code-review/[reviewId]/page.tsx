"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "../../../lib/api";

type Finding = {
  id: string; file_path: string; line_start: number | null; line_end: number | null;
  title: string; description: string; reasoning: string; severity: string; category: string; evidence: string;
  recommendation: string; source: string; analyzer: string; rule_id: string | null; confidence: number | null; status: string;
};
type Analyzer = { analyzer: string; status: string; exit_code: number | null; duration_ms: number; message: string | null };
type Review = {
  id: string; title: string; language: string; review_status: string; summary: string;
  total_findings: number; critical_count: number; high_count: number; medium_count: number;
  low_count: number; informational_count: number; execution_duration: number;
  configuration: { analyzers?: Analyzer[] }; files: { path: string; sha256: string }[]; findings: Finding[];
};
type PatchPreview = { file_path: string; original_sha256: string; unified_diff: string; explanation: string; applied: boolean; rolled_back?: boolean };

const badgeColor: Record<string, string> = {
  critical: "bg-red-100 text-red-800", high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100 text-amber-900", low: "bg-blue-100 text-blue-800",
  informational: "bg-slate-100 text-slate-700",
};

export default function ReviewDetailPage() {
  const router = useRouter();
  const params = useParams<{ reviewId: string }>();
  const [review, setReview] = useState<Review | null>(null);
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [fileFilter, setFileFilter] = useState("all");
  const [analyzerFilter, setAnalyzerFilter] = useState("all");
  const [status, setStatus] = useState("all");
  const [patch, setPatch] = useState<PatchPreview | null>(null);
  const [patchFinding, setPatchFinding] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setReview(await api<Review>(`/api/v1/reviews/${params.reviewId}`)); }
    catch (e) { const message = e instanceof Error ? e.message : "Could not load this review."; if (message.includes("401")) router.replace("/login"); else setError(message); }
  }, [params.reviewId, router]);
  useEffect(() => { void load(); }, [load]);

  const findings = useMemo(() => (review?.findings ?? []).filter((item) =>
    (severity === "all" || item.severity === severity) &&
    (category === "all" || item.category === category) &&
    (fileFilter === "all" || item.file_path === fileFilter) &&
    (analyzerFilter === "all" || item.analyzer === analyzerFilter) &&
    (status === "all" || item.status === status)), [review, severity, category, fileFilter, analyzerFilter, status]);

  async function updateFinding(item: Finding, next: string) {
    setError("");
    try {
      await api(`/api/v1/reviews/${params.reviewId}/findings/${item.id}`, { method: "PATCH", body: JSON.stringify({ status: next }) });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update finding."); }
  }
  async function previewPatch(item: Finding) {
    setBusy(true); setPatchFinding(item.id); setPatch(null); setError("");
    try { setPatch(await api<PatchPreview>(`/api/v1/reviews/${params.reviewId}/findings/${item.id}/patch`, { method: "POST" })); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not generate a patch preview."); }
    finally { setBusy(false); }
  }
  async function approvePatch() {
    if (!patch) return;
    setBusy(true); setError("");
    try {
      const result = await api<PatchPreview>(`/api/v1/reviews/${params.reviewId}/findings/${patchFinding}/patch/apply`, { method: "POST", body: JSON.stringify({ approved: true }) });
      setPatch(result); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not apply patch to uploaded source."); }
    finally { setBusy(false); }
  }
  async function approveRollback() {
    if (!window.confirm("Restore the previous uploaded source snapshot?")) return;
    setBusy(true); setError("");
    try {
      const result = await api<PatchPreview>(`/api/v1/reviews/${params.reviewId}/findings/${patchFinding}/patch/rollback`, { method: "POST", body: JSON.stringify({ approved: true }) });
      setPatch(result); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not roll back the approved patch."); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-[#fafbf8] text-[#20291e]"><header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4"><Link href="/dashboard" className="font-bold">DevPilot AI</Link><nav className="flex gap-4 text-sm"><Link href="/code-review">New review</Link><Link href="/settings/ai">AI settings</Link><Link href="/dashboard">Projects</Link></nav></div></header>
    <div className="mx-auto max-w-7xl px-5 py-8"><Link href="/code-review" className="text-sm text-[#62715d] hover:underline">← All reviews</Link>{error && <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
      {!review ? <p className="mt-8 text-sm text-[#748174]">Loading review…</p> : <>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-wider text-[#748174]">{review.language} · {review.review_status} · {review.execution_duration} ms</p><h1 className="mt-1 text-3xl font-semibold">{review.title}</h1><p className="mt-2 max-w-3xl text-sm text-[#667361]">{review.summary}</p></div><div className="flex gap-2"><span className="rounded-full bg-[#f1f5e8] px-3 py-1.5 text-sm">{review.total_findings} findings</span><span className="rounded-full bg-white px-3 py-1.5 text-sm">{review.files.length} source file(s)</span></div></div>
        <section className="mt-6 grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">{[["Critical", review.critical_count], ["High", review.high_count], ["Medium", review.medium_count], ["Low", review.low_count], ["Info", review.informational_count]].map(([label, count]) => <article key={String(label)} className="rounded-xl border border-[#E7EDE2] bg-white p-4"><p className="text-xs text-[#748174]">{label}</p><p className="mt-1 text-2xl font-semibold">{count}</p></article>)}</section>
        <section className="mt-6 rounded-2xl border border-[#E7EDE2] bg-white p-5"><h2 className="font-semibold">Analyzer execution</h2><div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{(review.configuration.analyzers ?? []).map((item) => <div key={item.analyzer} className="rounded-xl bg-[#f7f9f4] p-3"><div className="flex justify-between gap-2"><strong className="text-sm">{item.analyzer}</strong><span className="text-xs font-medium">{item.status.replaceAll("_", " ")}</span></div><p className="mt-1 text-xs text-[#748174]">{item.duration_ms} ms{item.exit_code !== null ? ` · exit ${item.exit_code}` : ""}</p>{item.message && <p className="mt-2 text-xs text-amber-800">{item.message}</p>}</div>)}</div></section>
        <section className="mt-6 rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Findings <span className="font-normal text-[#748174]">({findings.length})</span></h2><div className="flex flex-wrap gap-2"><select aria-label="Filter severity" value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded-lg border border-[#dfe7d8] px-2 py-1.5 text-sm"><option value="all">All severities</option>{["critical", "high", "medium", "low", "informational"].map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter category" value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-[#dfe7d8] px-2 py-1.5 text-sm"><option value="all">All categories</option>{[...new Set((review.findings).map((item) => item.category))].map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter file" value={fileFilter} onChange={(e) => setFileFilter(e.target.value)} className="rounded-lg border border-[#dfe7d8] px-2 py-1.5 text-sm"><option value="all">All files</option>{review.files.map((file) => <option key={file.path}>{file.path}</option>)}</select><select aria-label="Filter analyzer" value={analyzerFilter} onChange={(e) => setAnalyzerFilter(e.target.value)} className="rounded-lg border border-[#dfe7d8] px-2 py-1.5 text-sm"><option value="all">All analyzers</option>{[...new Set(review.findings.map((item) => item.analyzer))].map((item) => <option key={item}>{item}</option>)}</select><select aria-label="Filter status" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-[#dfe7d8] px-2 py-1.5 text-sm"><option value="all">All statuses</option>{["open", "accepted", "dismissed", "fixed"].map((item) => <option key={item}>{item}</option>)}</select></div></div>
          {findings.length === 0 ? <p className="mt-5 rounded-xl border border-dashed border-[#d6dfcf] px-4 py-8 text-center text-sm text-[#748174]">No findings match these filters.</p> : <ul className="mt-3 divide-y divide-[#edf1e9]">{findings.map((item) => <li key={item.id} className="py-5"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${badgeColor[item.severity] ?? badgeColor.informational}`}>{item.severity}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">{item.source === "ai" ? "AI observation" : item.analyzer + (item.rule_id ? " · " + item.rule_id : "")}</span><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs">{item.status}</span><span className="text-xs text-[#748174]">{item.category.replaceAll("_", " ")}</span></div><h3 className="mt-2 font-semibold">{item.title}</h3><p className="mt-1 text-xs text-[#748174]">{item.file_path}{item.line_start ? `:${item.line_start}${item.line_end && item.line_end !== item.line_start ? `–${item.line_end}` : ""}` : ""}</p><p className="mt-2 text-sm leading-6">{item.description}</p>{item.reasoning && <p className="mt-2 text-sm text-[#667361]"><strong>Why it matters:</strong> {item.reasoning}</p>}{item.evidence && <pre className="mt-3 overflow-x-auto rounded-xl bg-[#f6f8f3] p-3 text-xs leading-5"><code>{item.evidence}</code></pre>}{item.source === "ai" && item.confidence !== null && <p className="mt-2 text-xs text-[#748174]">AI confidence estimate: {Math.round(item.confidence * 100)}% · validate manually before relying on this observation.</p>}<p className="mt-3 text-sm"><strong>Suggested remediation:</strong> {item.recommendation}</p><div className="mt-3 flex flex-wrap gap-2"><button onClick={() => void updateFinding(item, "accepted")} className="rounded-lg border border-[#dfe7d8] px-3 py-1.5 text-xs">Accept</button><button onClick={() => void updateFinding(item, "dismissed")} className="rounded-lg border border-[#dfe7d8] px-3 py-1.5 text-xs">Dismiss</button><button onClick={() => void updateFinding(item, "fixed")} className="rounded-lg border border-[#dfe7d8] px-3 py-1.5 text-xs">Mark fixed</button><button disabled={busy || item.status === "fixed"} onClick={() => void previewPatch(item)} className="rounded-lg bg-[#B7F34A] px-3 py-1.5 text-xs font-semibold disabled:opacity-50">{busy && patchFinding === item.id ? "Generating…" : "Preview AI patch"}</button></div></li>)}</ul>}
        </section>
      </>}
      {patch && <section className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><div role="dialog" aria-modal="true" aria-labelledby="patch-title" className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"><div className="flex items-center justify-between"><h2 id="patch-title" className="text-lg font-semibold">Patch preview</h2><button onClick={() => setPatch(null)} aria-label="Close preview" className="rounded-lg px-3 py-1 hover:bg-slate-100">Close</button></div><p className="mt-2 text-sm text-[#667361]">{patch.explanation}</p><p className="mt-1 text-xs text-[#748174]">Target: {patch.file_path} · Uploaded snapshot only</p><pre className="mt-4 max-h-[50vh] overflow-auto rounded-xl bg-[#172016] p-4 text-xs leading-5 text-[#e8f4de]"><code>{patch.unified_diff}</code></pre>{patch.applied ? <><p role="status" className="mt-4 rounded-lg bg-[#f1f8e8] p-3 text-sm">Approved patch applied to the stored uploaded-source snapshot. No host or repository files were modified.</p><button disabled={busy} onClick={() => void approveRollback()} className="mt-3 rounded-lg border border-[#dfe7d8] px-4 py-2 text-sm">Approve rollback</button></> : patch.rolled_back ? <p role="status" className="mt-4 rounded-lg bg-[#f1f8e8] p-3 text-sm">The previous uploaded source was restored.</p> : <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-medium text-amber-900">This changes the stored review copy only.</p><p className="mt-1 text-xs text-amber-800">Review the diff first. Applying it records your approval and is allowed only while the original source hash still matches.</p><button disabled={busy} onClick={() => void approvePatch()} className="mt-3 rounded-lg bg-[#B7F34A] px-4 py-2 text-sm font-semibold disabled:opacity-50">I approve this patch</button></div>}</div></section>}
    </div>
  </main>;
}
