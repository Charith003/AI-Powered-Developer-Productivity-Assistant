"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, Project } from "../../lib/api";

type Generation = {
  id: string; title: string; project_id: string | null; review_finding_id: string | null;
  source_path: string; language: string; framework: string; generation_status: string;
  test_plan: { target: string; objective: string; category: string; priority: string }[];
  generated_test_content: string; validation_status: string; validation_errors: string[];
};
type Execution = {
  id: string; generation_id: string; execution_status: string; cancel_requested: boolean; total_tests: number;
  passed_tests: number; failed_tests: number; skipped_tests: number; error_count: number;
  line_coverage: number | null; branch_coverage: number | null; uncovered_lines: Record<string, number[]>;
  file_coverage: Record<string, { statements: number; covered_statements: number; line_percent: number | null; branch_percent: number | null }>;
  stdout: string; stderr: string; infrastructure_message: string | null; execution_duration: number;
};
type TestCase = { id: string; test_name: string; test_file: string; status: string; duration: number | null; error_message: string | null; traceback: string | null };
type TestSummary = { total_generations: number; total_executions: number; passed_tests: number; failed_tests: number; average_line_coverage: number | null; recent_executions: Execution[] };

export default function TestGeneratorPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [history, setHistory] = useState<Generation[]>([]);
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [summary, setSummary] = useState<TestSummary | null>(null);
  const [source, setSource] = useState("def add(a, b):\n    return a + b\n");
  const [testCode, setTestCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [projectRows, generations, metrics] = await Promise.all([
        api<Project[]>("/api/v1/projects"),
        api<Generation[]>("/api/v1/tests?limit=20"),
        api<TestSummary>("/api/v1/tests/summary"),
      ]);
      setProjects(projectRows); setHistory(generations); setSummary(metrics);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load test workspace"); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!execution) return;
    if (!["queued", "running"].includes(execution.execution_status)) {
      if (["completed", "failed", "error"].includes(execution.execution_status)) {
        void api<TestCase[]>(`/api/v1/tests/executions/${execution.id}/cases`).then(setTestCases).catch(() => setTestCases([]));
      }
      return;
    }
    const timer = window.setInterval(async () => {
      try { setExecution(await api<Execution>(`/api/v1/tests/executions/${execution.id}`)); }
      catch (e) { setError(e instanceof Error ? e.message : "Unable to refresh execution"); }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [execution]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setExecution(null);
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<Generation>("/api/v1/tests/generate", { method: "POST", body: JSON.stringify({
        title: data.get("title"), project_id: data.get("project_id") || null,
        source_path: data.get("source_path"), source_content: source, language: "python", framework: "pytest",
        categories: ["normal", "boundary", "negative", "exception"],
      }) });
      setGeneration(result); setTestCode(result.generated_test_content); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Test generation failed"); }
    finally { setBusy(false); }
  }
  async function openGeneration(item: Generation) {
    setError("");
    try { const result = await api<Generation>(`/api/v1/tests/${item.id}`); setGeneration(result); setTestCode(result.generated_test_content); setExecution(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load test generation"); }
  }
  async function save() {
    if (!generation) return;
    setBusy(true); setError("");
    try { const result = await api<Generation>(`/api/v1/tests/${generation.id}`, { method: "PATCH", body: JSON.stringify({ test_code: testCode }) }); setGeneration(result); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save test code"); }
    finally { setBusy(false); }
  }
  async function validate() {
    if (!generation) return;
    setBusy(true); setError("");
    try { const result = await api<Generation>(`/api/v1/tests/${generation.id}/validate`, { method: "POST" }); setGeneration(result); }
    catch (e) { setError(e instanceof Error ? e.message : "Validation failed"); }
    finally { setBusy(false); }
  }
  async function execute() {
    if (!generation) return;
    setBusy(true); setError("");
    try { setTestCases([]); setExecution(await api<Execution>(`/api/v1/tests/${generation.id}/execute`, { method: "POST" })); }
    catch (e) { setError(e instanceof Error ? e.message : "Execution could not be queued"); }
    finally { setBusy(false); }
  }
  async function cancelExecution() {
    if (!execution) return;
    try { setExecution(await api<Execution>(`/api/v1/tests/executions/${execution.id}/cancel`, { method: "POST" })); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not request execution cancellation"); }
  }
  async function analyzeFailures() {
    if (!execution) return;
    setBusy(true); setError("");
    try { await api(`/api/v1/tests/executions/${execution.id}/analyze-failures`, { method: "POST" }); setError("AI recommendations are saved with the execution and are not verified fixes."); }
    catch (e) { setError(e instanceof Error ? e.message : "Failure analysis failed"); }
    finally { setBusy(false); }
  }

  return <main className="min-h-screen bg-[#f7f9f4]"><header className="border-b border-[#E7EDE2] bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4"><Link href="/dashboard" className="font-bold">DevPilot AI</Link><nav className="flex gap-4 text-sm"><Link href="/dashboard">Dashboard</Link><Link href="/code-review">Code review</Link></nav></div></header>
    <div className="mx-auto max-w-6xl px-5 py-9"><p className="text-sm text-[#748174]">Engineering workflow</p><h1 className="mt-1 text-3xl font-semibold">Test generator</h1><p className="mt-2 text-[#748174]">Generate Pytest cases, validate them, then submit them to the isolated execution worker.</p>
      {summary && <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">{[["Generations", summary.total_generations], ["Executions", summary.total_executions], ["Passed", summary.passed_tests], ["Failed", summary.failed_tests], ["Avg. line coverage", summary.average_line_coverage === null ? "Unavailable" : `${summary.average_line_coverage}%`]].map(([label, value]) => <article key={String(label)} className="rounded-xl border border-[#E7EDE2] bg-white p-3"><p className="text-xs text-[#748174]">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></article>)}</section>}
      {error && <p role="alert" className="mt-4 rounded-xl bg-white p-3 text-sm text-[#a44444]">{error}</p>}
      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[0.8fr_1.2fr]"><form onSubmit={generate} className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><h2 className="font-semibold">Source and test plan</h2><label className="mt-4 block text-sm">Title<input name="title" defaultValue="Generated tests" className="mt-1 w-full rounded-lg border p-2" /></label><label className="mt-3 block text-sm">Project (optional)<select name="project_id" className="mt-1 w-full rounded-lg border bg-white p-2"><option value="">No project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label className="mt-3 block text-sm">Python source path<input name="source_path" defaultValue="math_ops.py" required className="mt-1 w-full rounded-lg border p-2" /></label><label className="mt-3 block text-sm">Python source<textarea value={source} onChange={(event) => setSource(event.target.value)} rows={12} maxLength={65536} className="mt-1 w-full rounded-lg border p-3 font-mono text-xs" /></label><p className="mt-2 text-xs text-[#748174]">Python/Pytest is active first. Source and generated test are capped at 64 KiB each.</p><button disabled={busy} className="mt-4 w-full rounded-xl bg-[#B7F34A] px-4 py-2.5 font-semibold disabled:opacity-60">{busy ? "Working…" : "Generate tests with AI"}</button></form>
      <section className="space-y-5">{generation ? <><article className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">{generation.title}</h2><p className="text-sm text-[#748174]">{generation.language} · {generation.framework} · validation: {generation.validation_status}</p></div><div className="flex gap-2"><button onClick={() => void validate()} disabled={busy} className="rounded-lg border px-3 py-2 text-sm">Validate</button><button onClick={() => void save()} disabled={busy} className="rounded-lg border px-3 py-2 text-sm">Save edits</button><button onClick={() => void execute()} disabled={busy || generation.validation_status !== "valid"} className="rounded-lg bg-[#B7F34A] px-3 py-2 text-sm font-semibold disabled:opacity-50">Queue execution</button></div></div>{generation.validation_errors.map((item) => <p key={item} className="mt-2 text-sm text-red-700">{item}</p>)}<textarea value={testCode} onChange={(event) => setTestCode(event.target.value)} rows={16} className="mt-4 w-full rounded-lg border bg-[#fbfcfa] p-3 font-mono text-xs" /></article><article className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><h3 className="font-semibold">Structured test plan</h3><ul className="mt-3 space-y-2">{generation.test_plan.map((item, index) => <li key={`${item.target}-${index}`} className="rounded-lg bg-[#f7f9f4] p-3 text-sm"><span className="font-medium">{item.target}</span> · {item.category} · {item.priority}<p className="mt-1 text-[#748174]">{item.objective}</p></li>)}</ul></article></> : <article className="rounded-2xl border border-dashed border-[#d6dfcf] bg-white p-8 text-center text-sm text-[#748174]">Generate or select a saved generation to review its test plan.</article>}
      {execution && <article className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Execution results</h2><span className="rounded-full bg-[#f7f9f4] px-3 py-1 text-sm">{execution.execution_status}</span>{["queued", "running"].includes(execution.execution_status) && <button onClick={() => void cancelExecution()} disabled={execution.cancel_requested} className="rounded-lg border px-3 py-1 text-xs disabled:opacity-50">{execution.cancel_requested ? "Cancelling…" : execution.execution_status === "running" ? "Request cancellation" : "Cancel queued job"}</button>}</div>{execution.infrastructure_message && <p className="mt-3 text-sm text-amber-800">{execution.infrastructure_message}</p>}{["completed", "failed", "error"].includes(execution.execution_status) && <><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">{[["Total", execution.total_tests], ["Passed", execution.passed_tests], ["Failed", execution.failed_tests], ["Skipped / errors", `${execution.skipped_tests} / ${execution.error_count}`]].map(([name, value]) => <div key={String(name)} className="rounded-lg bg-[#f7f9f4] p-3"><p className="text-xs text-[#748174]">{name}</p><p className="text-xl font-semibold">{value}</p></div>)}</div>{testCases.length > 0 && <div className="mt-4 space-y-2"><h3 className="text-sm font-semibold">Test cases</h3>{testCases.map((test) => <details key={test.id} className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{test.status.toUpperCase()} · {test.test_name} · {test.duration ?? 0}s</summary>{test.error_message && <p className="mt-2 text-sm text-red-700">{test.error_message}</p>}{test.traceback && <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs">{test.traceback}</pre>}</details>)}</div>}<p className="mt-3 text-sm">Line coverage: {execution.line_coverage === null ? "Unavailable" : `${execution.line_coverage}%`} · Branch coverage: {execution.branch_coverage === null ? "Unavailable" : `${execution.branch_coverage}%`} · {execution.execution_duration} ms</p>{Object.keys(execution.file_coverage).length > 0 && <div className="mt-3 rounded-lg bg-[#f7f9f4] p-3 text-sm"><p className="font-medium">File coverage</p>{Object.entries(execution.file_coverage).map(([file, coverage]) => <p key={file} className="mt-1 text-[#748174]">{file}: {coverage.line_percent === null ? "Unavailable" : `${coverage.line_percent}% lines`} · {coverage.branch_percent === null ? "branch unavailable" : `${coverage.branch_percent}% branches`} · {coverage.covered_statements}/{coverage.statements} statements</p>)}</div>}{Object.keys(execution.uncovered_lines).length > 0 && <div className="mt-3 rounded-lg bg-[#f7f9f4] p-3 text-sm"><p className="font-medium">Uncovered lines</p>{Object.entries(execution.uncovered_lines).map(([file, lines]) => <p key={file} className="mt-1 text-[#748174]">{file}: {lines.join(", ")}</p>)}</div>}<pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-[#172018] p-3 text-xs text-white">{execution.stderr || execution.stdout || "No output recorded."}</pre>{execution.failed_tests + execution.error_count > 0 && <button onClick={() => void analyzeFailures()} className="mt-3 rounded-lg border px-3 py-2 text-sm">Ask AI to explain actual failures</button>}</>}</article>}
      <article className="rounded-2xl border border-[#E7EDE2] bg-white p-5"><h2 className="font-semibold">Generation history</h2>{history.length ? <ul className="mt-3 divide-y">{history.map((item) => <li key={item.id} className="py-2"><button onClick={() => void openGeneration(item)} className="text-left"><span className="text-sm font-medium hover:underline">{item.title}</span><span className="ml-2 text-xs text-[#748174]">{item.framework} · {item.validation_status}</span></button></li>)}</ul> : <p className="mt-2 text-sm text-[#748174]">No saved test generations yet.</p>}</article></section></div>
      <p className="mt-5 text-xs text-[#748174]">Execution requires a separate worker and a digest-pinned sandbox image. The API never runs source or test code.</p>
    </div></main>;
}
