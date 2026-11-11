"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Project } from "../../lib/api";

type ReviewItem = {
  id: string; title: string; language: string; review_status: string; summary: string;
  total_findings: number; critical_count: number; high_count: number; created_at: string;
};
const analyzers: Record<string, string[]> = {
  python: ["ruff", "bandit", "pylint"], javascript: ["eslint"],
  typescript: ["eslint", "tsc"], java: ["checkstyle"], c: ["clang"], cpp: ["clang"],
};

export default function CodeReviewPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [history, setHistory] = useState<ReviewItem[]>([]);
  const [language, setLanguage] = useState("auto");
  const [selectedAnalyzers, setSelectedAnalyzers] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [aiEnabled, setAiEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([api<Project[]>("/api/v1/projects"), api<ReviewItem[]>("/api/v1/reviews?limit=20")])
      .then(([projectItems, reviews]) => { setProjects(projectItems); setHistory(reviews); })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : "Unable to load code review workspace.";
        if (message.includes("401")) router.replace("/login"); else setError(message);
      });
  }, [router]);

  function languageChanged(value: string) {
    setLanguage(value);
    setSelectedAnalyzers(value === "auto" ? [] : value === "python" ? ["ruff", "bandit"] : [...(analyzers[value] ?? [])]);
  }

  async function loadFile(event: ChangeEvent<HTMLInputElement>) {
    setError("");
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 65_536) { setError("Source files are limited to 64 KiB."); return; }
    try { setPath(file.name); setContent(await file.text()); }
    catch { setError("Could not read this file as UTF-8 text."); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const analyzersToRun = language === "auto" ? null : selectedAnalyzers;
    try {
      const review = await api<{ id: string }>("/api/v1/reviews", {
        method: "POST",
        body: JSON.stringify({
          title: data.get("title"), project_id: data.get("project_id") || null,
          language, files: [{ path, content }], analyzers: analyzersToRun, ai_enabled: aiEnabled,
        }),
      });
      router.push(`/code-review/${review.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to create review."); }
    finally { setBusy(false); }
  }

  return <main className="min-h-screen bg-[#fafbf8] text-[#20291e]">
    <header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4"><Link href="/dashboard" className="font-bold">DevPilot AI</Link><nav className="flex gap-4 text-sm"><Link href="/dashboard">Projects</Link><Link href="/settings/ai">AI settings</Link><Link href="/settings/profile">Profile</Link></nav></div></header>
    <div className="mx-auto grid max-w-7xl gap-8 px-5 py-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(300px,0.75fr)]">
      <section><p className="text-sm font-medium text-[#748174]">Engineering tools</p><h1 className="mt-1 text-3xl font-semibold">Code review</h1><p className="mt-2 text-[#667361]">Run deterministic analyzers and optional evidence-checked AI review against uploaded source.</p>
        {error && <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
        <form onSubmit={submit} className="mt-6 space-y-5 rounded-2xl border border-[#E7EDE2] bg-white p-5 shadow-sm">
          <label className="block text-sm font-medium">Review title<input name="title" maxLength={160} defaultValue="Code review" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5" /></label>
          <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium">Project (optional)<select name="project_id" defaultValue="" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] bg-white px-3 py-2.5"><option value="">No project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="block text-sm font-medium">Language<select value={language} onChange={(event) => languageChanged(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] bg-white px-3 py-2.5"><option value="auto">Detect from filename</option>{Object.keys(analyzers).map((name) => <option key={name} value={name}>{name === "cpp" ? "C++" : name[0].toUpperCase() + name.slice(1)}</option>)}</select></label></div>
          <label className="block text-sm font-medium">Source file<input type="file" accept=".py,.pyi,.js,.jsx,.mjs,.cjs,.ts,.tsx,.java,.c,.h,.cc,.cpp,.cxx,.hpp,.hh" onChange={(event) => void loadFile(event)} className="mt-1.5 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-[#eff5e6] file:px-3 file:py-2" /><span className="mt-1 block text-xs font-normal text-[#748174]">UTF-8 source only · maximum 64 KiB per file</span></label>
          <label className="block text-sm font-medium">Path in project<textarea value={path} onChange={(event) => setPath(event.target.value)} required maxLength={160} rows={1} placeholder="src/module.py" className="mt-1.5 w-full rounded-xl border border-[#dfe7d8] px-3 py-2.5 font-mono text-sm" /></label>
          <label className="block text-sm font-medium">Source code<textarea value={content} onChange={(event) => setContent(event.target.value)} required maxLength={65_536} rows={14} spellCheck={false} placeholder="Paste source code or choose a file above…" className="mt-1.5 w-full resize-y rounded-xl border border-[#dfe7d8] px-3 py-3 font-mono text-sm leading-6" /></label>
          {language !== "auto" && <fieldset className="rounded-xl border border-[#e7ede2] p-4"><legend className="px-1 text-sm font-medium">Requested analyzers</legend><div className="flex flex-wrap gap-x-5 gap-y-2">{(analyzers[language] ?? []).map((name) => <label key={name} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedAnalyzers.includes(name)} onChange={(event) => setSelectedAnalyzers((current) => event.target.checked ? [...current, name] : current.filter((item) => item !== name))} />{name}</label>)}</div><p className="mt-2 text-xs text-[#748174]">Unavailable tools are shown explicitly in the review report.</p></fieldset>}
          <label className="flex items-start gap-3 rounded-xl bg-[#f7fbed] p-4 text-sm"><input type="checkbox" checked={aiEnabled} onChange={(event) => setAiEnabled(event.target.checked)} className="mt-0.5" /><span><strong>AI-assisted contextual review</strong><span className="mt-1 block text-xs text-[#667361]">Uses the configured backend provider. Credential-like values are redacted before submission; findings are kept only when quoted evidence matches the source.</span></span></label>
          <button disabled={busy || !content.trim() || !path.trim()} className="rounded-xl bg-[#B7F34A] px-5 py-3 font-semibold disabled:cursor-not-allowed disabled:opacity-50">{busy ? "Running analysis…" : "Start code review"}</button>
        </form>
      </section>
      <aside><div className="sticky top-6 rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="font-semibold">Review history</h2><p className="mt-1 text-sm text-[#748174]">Your latest persisted runs</p></div><span className="rounded-full bg-[#f3f6ee] px-2.5 py-1 text-xs">{history.length}</span></div>{history.length === 0 ? <p className="mt-6 rounded-xl border border-dashed border-[#d6dfcf] px-4 py-8 text-center text-sm text-[#748174]">Completed reviews will appear here.</p> : <ul className="mt-4 divide-y divide-[#edf1e9]">{history.map((item) => <li key={item.id} className="py-3"><Link href={`/code-review/${item.id}`} className="font-medium hover:underline">{item.title}</Link><p className="mt-1 text-xs text-[#748174]">{item.language} · {item.review_status} · {item.total_findings} findings</p><p className="mt-1 text-xs text-[#748174]">{new Date(item.created_at).toLocaleString()}</p></li>)}</ul>}</div></aside>
    </div>
  </main>;
}
