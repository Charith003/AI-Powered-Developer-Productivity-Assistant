"use client";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Project, Profile } from "../../lib/api";

type ReviewSummary = {
  total_reviews: number; total_findings: number; open_findings: number;
  critical_count: number; high_count: number; medium_count: number; low_count: number;
  informational_count: number;
  recent_reviews: { id: string; title: string; language: string; review_status: string; total_findings: number; created_at: string }[];
  daily_reviews: { date: string; count: number }[];
};
type TestSummary = { total_generations: number; total_executions: number; passed_tests: number; failed_tests: number; average_line_coverage: number | null };

export default function DashboardPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null);
  const [testSummary, setTestSummary] = useState<TestSummary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const me = await api<Profile>("/api/v1/auth/me"); setProfile(me);
      setProjects(await api<Project[]>("/api/v1/projects"));
      setReviewSummary(await api<ReviewSummary>("/api/v1/reviews/summary"));
      setTestSummary(await api<TestSummary>("/api/v1/tests/summary"));
    } catch { router.replace("/login"); }
  }, [router]);
  useEffect(() => { void load(); }, [load]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const project = await api<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify({ name: form.get("name"), description: form.get("description") }) });
      setProjects((items) => [project, ...items]); event.currentTarget.reset();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create project"); }
    finally { setBusy(false); }
  }
  async function rename(project: Project) {
    const name = window.prompt("Project name", project.name)?.trim(); if (!name || name === project.name) return;
    try {
      const updated = await api<Project>(`/api/v1/projects/${project.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
      setProjects((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not rename project"); }
  }
  async function remove(id: string) {
    if (!window.confirm("Delete this project? This cannot be undone.")) return;
    try { await api<void>(`/api/v1/projects/${id}`, { method: "DELETE" }); setProjects((items) => items.filter((item) => item.id !== id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not delete project"); }
  }
  async function logout() {
    await api<void>("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined); router.replace("/login");
  }
  return <main className="min-h-screen"><header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><Link href="/" className="font-bold">DevPilot AI</Link><div className="flex items-center gap-4 text-sm"><span className="hidden text-[#748174] sm:block">{profile?.email}</span><Link href="/code-review" className="font-medium">Code review</Link><Link href="/test-generator" className="font-medium">Test generator</Link><Link href="/settings/ai" className="font-medium">AI settings</Link><Link href="/settings/profile" className="font-medium">Profile</Link><button onClick={logout} className="font-medium">Sign out</button></div></div></header><div className="mx-auto max-w-6xl px-5 py-10"><p className="text-sm text-[#748174]">Workspace</p><h1 className="mt-1 text-3xl font-semibold">{profile ? `Welcome, ${profile.full_name}` : "Your projects"}</h1><p className="mt-2 text-[#748174]">Create and manage your project spaces.</p>
    <section className="mt-6 rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="font-semibold">Automated testing</h2><p className="mt-1 text-sm text-[#748174]">Persisted generation and execution metrics</p></div><Link href="/test-generator" className="rounded-lg bg-[#B7F34A] px-3 py-2 text-sm font-semibold">Open test generator</Link></div>{testSummary ? <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">{[["Generations", testSummary.total_generations], ["Executions", testSummary.total_executions], ["Passed tests", testSummary.passed_tests], ["Failed tests", testSummary.failed_tests], ["Average line coverage", testSummary.average_line_coverage === null ? "Unavailable" : `${testSummary.average_line_coverage}%`]].map(([label, value]) => <article key={String(label)} className="rounded-xl bg-[#f7f9f4] p-3"><p className="text-xs text-[#748174]">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></article>)}</div> : <p className="mt-4 text-sm text-[#748174]">Loading test metrics…</p>}</section>
    <section className="mt-7 rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Code review activity</h2><p className="mt-1 text-sm text-[#748174]">Metrics from your persisted review history</p></div><Link href="/code-review" className="rounded-lg bg-[#B7F34A] px-3 py-2 text-sm font-semibold">Start review</Link></div>{reviewSummary ? <><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">{[["Total reviews", reviewSummary.total_reviews], ["Total findings", reviewSummary.total_findings], ["Open findings", reviewSummary.open_findings], ["Critical / High", `${reviewSummary.critical_count} / ${reviewSummary.high_count}`], ["Medium / Low / Info", `${reviewSummary.medium_count} / ${reviewSummary.low_count} / ${reviewSummary.informational_count}`]].map(([label, value]) => <article key={String(label)} className="rounded-xl bg-[#f7f9f4] p-3"><p className="text-xs text-[#748174]">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></article>)}</div><div className="mt-5 grid gap-6 lg:grid-cols-2"><div><h3 className="text-sm font-medium">Last seven days</h3><div className="mt-3 flex h-24 items-end gap-2" aria-label="Reviews per day, last seven days">{reviewSummary.daily_reviews.map((day) => { const peak = Math.max(1, ...reviewSummary.daily_reviews.map((item) => item.count)); return <div key={day.date} className="flex flex-1 flex-col items-center gap-1"><span className="text-[10px] text-[#748174]">{day.count}</span><div className="w-full rounded-t bg-[#B7F34A]" style={{ height: `${Math.max(4, (day.count / peak) * 62)}px` }} /><span className="text-[10px] text-[#748174]">{day.date.slice(5)}</span></div>; })}</div></div><div><h3 className="text-sm font-medium">Recent reviews</h3>{reviewSummary.recent_reviews.length ? <ul className="mt-2 divide-y divide-[#edf1e9]">{reviewSummary.recent_reviews.map((review) => <li key={review.id} className="py-2"><Link href={`/code-review/${review.id}`} className="text-sm font-medium hover:underline">{review.title}</Link><p className="text-xs text-[#748174]">{review.language} · {review.review_status} · {review.total_findings} findings</p></li>)}</ul> : <p className="mt-3 text-sm text-[#748174]">No code reviews yet.</p>}</div></div></> : <p className="mt-5 text-sm text-[#748174]">Loading review metrics…</p>}</section>
    <section className="mt-8 grid gap-7 lg:grid-cols-[0.8fr_1.2fr]"><form onSubmit={create} className="h-fit rounded-2xl border border-[#E7EDE2] bg-white p-5"><h2 className="font-semibold">New project</h2><label className="mt-4 block text-sm font-medium">Project name<input name="name" required maxLength={120} className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5" /></label><label className="mt-3 block text-sm font-medium">Description<textarea name="description" maxLength={5000} rows={3} className="mt-1.5 w-full resize-y rounded-xl border border-[#dfe7d8] px-3 py-2.5" /></label>{error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}<button disabled={busy} className="mt-4 w-full rounded-xl bg-[#B7F34A] px-4 py-2.5 font-semibold disabled:opacity-60">{busy ? "Creating…" : "Create project"}</button></form><div><div className="flex items-baseline justify-between"><h2 className="font-semibold">Projects</h2><span className="text-sm text-[#748174]">{projects.length} total</span></div>{projects.length === 0 ? <div className="mt-3 rounded-2xl border border-dashed border-[#d6dfcf] bg-white px-6 py-12 text-center"><p className="font-medium">No projects yet</p><p className="mt-1 text-sm text-[#748174]">Create a project to start building your workspace.</p></div> : <ul className="mt-3 space-y-3">{projects.map((project) => <li key={project.id} className="flex items-center justify-between gap-3 rounded-2xl border border-[#E7EDE2] bg-white p-5"><div><h3 className="font-semibold">{project.name}</h3><p className="mt-1 text-sm text-[#748174]">{project.description || "No description"}</p></div><div className="flex gap-2"><button onClick={() => void rename(project)} className="rounded-lg border border-[#dfe7d8] px-3 py-2 text-sm">Rename</button><button onClick={() => void remove(project.id)} className="rounded-lg border border-[#f0dada] px-3 py-2 text-sm text-[#a44444]">Delete</button></div></li>)}</ul>}</div></section></div></main>;
}
