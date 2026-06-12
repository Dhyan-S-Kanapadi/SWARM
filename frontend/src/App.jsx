import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  BrainCircuit,
  CheckCircle2,
  CircuitBoard,
  Code2,
  Download,
  FileCode2,
  Layers3,
  Loader2,
  Play,
  Rocket,
  Sparkles,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const STEPS = [
  { id: "analyst", label: "Product Analyst", icon: BrainCircuit },
  { id: "architect", label: "Software Architect", icon: CircuitBoard },
  { id: "builder", label: "SWARM Builder", icon: Code2 },
  { id: "pitcher", label: "Pitch Strategist", icon: Layers3 },
];

const SAMPLE_IDEA =
  "Build a salon appointment manager with customer profiles, staff schedules, service bookings, payment status, reminders, daily appointment queue, revenue metrics, and English/Hindi/Kannada labels.";

export default function App() {
  const [idea, setIdea] = useState(SAMPLE_IDEA);
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState(null);
  const [output, setOutput] = useState(null);
  const [artifacts, setArtifacts] = useState(null);
  const [demo, setDemo] = useState(null);
  const [selectedFile, setSelectedFile] = useState("");
  const [activeTab, setActiveTab] = useState("demo");
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState("");
  const [validationBusy, setValidationBusy] = useState(false);
  const [qualityBusy, setQualityBusy] = useState(false);
  const [error, setError] = useState("");
  const [isStarting, setIsStarting] = useState(false);

  const codeFiles = output?.code_files || {};
  const selectedFileContent = selectedFile ? codeFiles[selectedFile] : "";

  const runPhase = useMemo(() => {
    if (!runId) return "Ready";
    if (status?.done) return "Complete";
    if (status?.agent_statuses?.builder === "running") return "Building app";
    return "Agents running";
  }, [runId, status]);

  async function startRun(event) {
    event.preventDefault();
    const trimmed = idea.trim();
    if (!trimmed || isStarting) return;

    setIsStarting(true);
    setError("");
    setStatus(null);
    setOutput(null);
    setArtifacts(null);
    setDemo(null);
    setPreview(null);
    setQualityBusy(false);
    setSelectedFile("");
    setActiveTab("demo");

    try {
      const response = await fetch(`${API_BASE_URL}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea: trimmed }),
      });
      if (!response.ok) throw new Error(`Unable to start run (${response.status})`);
      const data = await response.json();
      setRunId(data.run_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsStarting(false);
    }
  }

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    let interval = null;

    async function refresh() {
      try {
        const statusResponse = await fetch(`${API_BASE_URL}/status/${runId}`);
        if (!statusResponse.ok) throw new Error(`Unable to load status (${statusResponse.status})`);
        const nextStatus = await statusResponse.json();
        if (cancelled) return;
        setStatus(nextStatus);

        if (nextStatus.done || nextStatus.agent_statuses?.builder === "waiting_for_trae") {
          const [outputResponse, artifactResponse, demoResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/output/${runId}`),
            fetch(`${API_BASE_URL}/artifacts/${runId}`),
            fetch(`${API_BASE_URL}/demo/${runId}`),
          ]);
          if (outputResponse.ok) {
            const nextOutput = await outputResponse.json();
            if (!cancelled) {
              setOutput(nextOutput);
              const paths = Object.keys(nextOutput.code_files || {});
              setSelectedFile((current) => current || paths[0] || "");
            }
          }
          if (artifactResponse.ok) {
            const nextArtifacts = await artifactResponse.json();
            if (!cancelled) setArtifacts(nextArtifacts);
          }
          if (demoResponse.ok) {
            const nextDemo = await demoResponse.json();
            if (!cancelled) setDemo(nextDemo);
          }
          const previewResponse = await fetch(`${API_BASE_URL}/preview/${runId}/status`);
          if (previewResponse.ok && !cancelled) {
            setPreview(await previewResponse.json());
          }
        }

        if (nextStatus.done && interval) clearInterval(interval);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    interval = setInterval(refresh, 2500);
    refresh();
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runId]);

  async function runPreviewAction(action) {
    if (!runId || previewBusy) return;
    setPreviewBusy(action);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/preview/${runId}/${action}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : `Preview ${action} failed`);
      }
      setPreview(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setPreviewBusy("");
    }
  }

  async function runValidation() {
    if (!runId || validationBusy) return;
    setValidationBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/validate/${runId}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Validation failed");
      }
      setArtifacts((current) => ({ ...(current || {}), validation: data }));
      setDemo((current) =>
        current
          ? {
              ...current,
              delivery: {
                ...current.delivery,
                validation_status: data.status,
                validation_checks: (data.checks || []).map((check) => ({
                  name: check.name,
                  returncode: check.returncode,
                  duration_seconds: check.duration_seconds,
                })),
              },
            }
          : current,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setValidationBusy(false);
    }
  }

  async function runQualityCheck() {
    if (!runId || qualityBusy) return;
    setQualityBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/quality/${runId}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Quality check failed");
      }
      setArtifacts((current) => ({ ...(current || {}), quality: data }));
      setDemo((current) =>
        current
          ? {
              ...current,
              delivery: {
                ...current.delivery,
                quality_score: data.score,
                quality_grade: data.grade,
              },
            }
          : current,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setQualityBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#111827]">
      <section className="border-b border-[#d9dee7] bg-[#0d1b2a] text-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
          <div className="flex flex-col justify-between gap-8">
            <div>
              <div className="inline-flex items-center gap-2 rounded-md border border-white/15 bg-white/10 px-3 py-2 text-sm text-[#dbeafe]">
                <Sparkles className="h-4 w-4 text-[#fbbf24]" />
                SWARM.AI founder workspace
              </div>
              <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
                Plain local-business problem to working operations app.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-[#cbd5e1]">
                Analyst, architect, SWARM builder, and pitch strategist turn one prompt into a runnable app with customer records, local-language UX, dashboard metrics, validation, and live preview links.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="Phase" value={runPhase} />
              <Metric label="Files" value={artifacts?.artifact_counts?.code_files ?? 0} />
              <Metric label="Pitch fields" value={artifacts?.artifact_counts?.pitch_deck_fields ?? 0} />
              <Metric label="Errors" value={status?.errors?.length ?? 0} />
            </div>
          </div>

          <form onSubmit={startRun} className="rounded-lg border border-white/10 bg-white p-4 text-[#111827] shadow-2xl">
            <label className="text-sm font-semibold" htmlFor="idea">
              Local business problem
            </label>
            <textarea
              id="idea"
              rows={8}
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="Describe the local shop workflow you want to manage..."
              className="mt-3 min-h-48 w-full resize-y rounded-md border border-[#cfd6e3] bg-[#f8fafc] px-4 py-3 text-sm leading-6 outline-none transition focus:border-[#2563eb] focus:ring-2 focus:ring-[#bfdbfe]"
            />
            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                onClick={() => setIdea(SAMPLE_IDEA)}
                className="inline-flex items-center justify-center gap-2 rounded-md border border-[#cfd6e3] px-4 py-2 text-sm font-semibold text-[#334155] hover:bg-[#f1f5f9]"
              >
                <Sparkles className="h-4 w-4" />
                Load demo idea
              </button>
              <button
                type="submit"
                disabled={!idea.trim() || isStarting}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#2563eb] px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#1d4ed8] disabled:cursor-not-allowed disabled:bg-[#94a3b8]"
              >
                {isStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                Generate app
              </button>
            </div>
          </form>
        </div>
      </section>

      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-[#fecaca] bg-[#fff1f2] px-4 py-3 text-sm text-[#9f1239]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <section className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-4">
            <RunCard runId={runId} status={status} artifacts={artifacts} />
            <AgentTimeline status={status} />
            <PreviewPanel
              runId={runId}
              artifacts={artifacts}
              preview={preview}
              busy={previewBusy}
              onAction={runPreviewAction}
            />
            <ValidationPanel
              artifacts={artifacts}
              busy={validationBusy}
              onValidate={runValidation}
            />
            <QualityPanel
              artifacts={artifacts}
              busy={qualityBusy}
              onCheck={runQualityCheck}
            />
          </aside>

          <section className="min-w-0 rounded-lg border border-[#d9dee7] bg-white shadow-sm">
            <div className="flex flex-wrap gap-2 border-b border-[#e5e7eb] px-4 py-3">
              {[
                ["demo", "Demo"],
                ["overview", "Overview"],
                ["requirements", "Requirements"],
                ["architecture", "Architecture"],
                ["code", "Code"],
                ["pitch", "Pitch Deck"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
                    activeTab === id ? "bg-[#111827] text-white" : "text-[#475569] hover:bg-[#f1f5f9]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="p-4">
              {activeTab === "demo" && <DemoMode demo={demo} preview={preview} runId={runId} />}
              {activeTab === "overview" && <Overview output={output} artifacts={artifacts} runId={runId} />}
              {activeTab === "requirements" && <Requirements requirements={output?.requirements} />}
              {activeTab === "architecture" && <Architecture architecture={output?.architecture} />}
              {activeTab === "code" && (
                <CodeExplorer
                  files={codeFiles}
                  selectedFile={selectedFile}
                  selectedFileContent={selectedFileContent}
                  onSelect={setSelectedFile}
                />
              )}
              {activeTab === "pitch" && <PitchDeck deck={output?.pitch_deck} />}
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/10 px-3 py-3">
      <p className="text-xs uppercase tracking-[0.12em] text-[#93c5fd]">{label}</p>
      <p className="mt-1 truncate text-lg font-semibold text-white">{String(value)}</p>
    </div>
  );
}

function RunCard({ runId, status, artifacts }) {
  return (
    <div className="rounded-lg border border-[#d9dee7] bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#64748b]">Run Control</p>
          <p className="mt-2 break-all font-mono text-sm text-[#0f172a]">{runId || "No active run"}</p>
        </div>
        <StatusPill status={status?.done ? "done" : status?.current_agent || "idle"} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Info label="Updated" value={formatTime(status?.updated_at)} />
        <Info label="App name" value={artifacts?.detected_app?.name || "Pending"} />
      </div>
      {runId && (artifacts?.artifact_counts?.code_files ?? 0) > 0 && (
        <a
          href={`${API_BASE_URL}/download/${runId}`}
          className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-[#111827] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1f2937]"
        >
          <Download className="h-4 w-4" />
          Download app zip
        </a>
      )}
    </div>
  );
}

function Info({ label, value }) {
  return (
    <div>
      <p className="text-xs text-[#64748b]">{label}</p>
      <p className="mt-1 truncate font-semibold text-[#111827]">{value}</p>
    </div>
  );
}

function AgentTimeline({ status }) {
  const statuses = status?.agent_statuses || {};
  return (
    <div className="rounded-lg border border-[#d9dee7] bg-white p-4 shadow-sm">
      <p className="text-sm font-semibold text-[#111827]">Agent timeline</p>
      <div className="mt-4 flex flex-col gap-3">
        {STEPS.map((step) => {
          const Icon = step.icon;
          const stepStatus = statuses[step.id] || "pending";
          return (
            <div key={step.id} className="flex items-center gap-3">
              <div className={`flex h-9 w-9 items-center justify-center rounded-md ${stepColor(stepStatus)}`}>
                {stepStatus === "running" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-[#1f2937]">{step.label}</p>
                <p className="text-xs uppercase tracking-[0.12em] text-[#64748b]">{stepStatus.replaceAll("_", " ")}</p>
              </div>
            </div>
          );
        })}
      </div>
      {(status?.errors || []).length > 0 && (
        <div className="mt-4 rounded-md bg-[#fff7ed] p-3 text-sm text-[#9a3412]">
          {status.errors.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function PreviewPanel({ runId, artifacts, preview, busy, onAction }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const running = preview?.running;
  return (
    <div className="rounded-lg border border-[#d9dee7] bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <Rocket className="mt-0.5 h-5 w-5 text-[#2563eb]" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#111827]">Generated app preview</p>
          <p className="mt-1 text-sm leading-6 text-[#475569]">
            Prepare and launch the SWARM-built app without leaving the workspace.
          </p>
        </div>
      </div>
      <PreviewButton
        disabled={!runId || !hasFiles || Boolean(busy)}
        onClick={() => onAction("launch")}
        label="Launch app"
        busy={busy === "launch"}
        primary
      />
      <div className="mt-4 grid grid-cols-2 gap-2">
        <PreviewButton disabled={!runId || !hasFiles || Boolean(busy)} onClick={() => onAction("prepare")} label="Prepare" busy={busy === "prepare"} />
        <PreviewButton disabled={!runId || !hasFiles || Boolean(busy)} onClick={() => onAction("install")} label="Install" busy={busy === "install"} />
        <PreviewButton disabled={!runId || !hasFiles || Boolean(busy)} onClick={() => onAction("start")} label="Start" busy={busy === "start"} />
        <PreviewButton disabled={!runId || !running || Boolean(busy)} onClick={() => onAction("stop")} label="Stop" busy={busy === "stop"} />
      </div>
      {preview?.frontend_url && running && (
        <a
          href={preview.frontend_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-[#16a34a] px-4 py-2 text-sm font-semibold text-white hover:bg-[#15803d]"
        >
          Open generated app <ArrowUpRight className="h-4 w-4" />
        </a>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <Info label="Prepared" value={preview?.prepared ? "Yes" : "No"} />
        <Info label="Installed" value={preview?.dependencies_installed ? "Yes" : "No"} />
      </div>
      {preview?.frontend_url && (
        <div className="mt-3 rounded-md border border-[#e5e7eb] bg-[#f8fafc] p-3 text-xs">
          <p className="font-semibold text-[#111827]">Generated app links</p>
          <a className="mt-2 block break-all font-mono text-[#2563eb]" href={preview.frontend_url} target="_blank" rel="noreferrer">
            {preview.frontend_url}
          </a>
          <a className="mt-1 block break-all font-mono text-[#2563eb]" href={`${preview.api_url}/api/health`} target="_blank" rel="noreferrer">
            {preview.api_url}/api/health
          </a>
        </div>
      )}
    </div>
  );
}

function PreviewButton({ label, busy, disabled, onClick, primary = false }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:bg-[#f1f5f9] disabled:text-[#94a3b8] ${
        primary
          ? "mt-4 border border-[#15803d] bg-[#16a34a] text-white hover:bg-[#15803d]"
          : "border border-[#cbd5e1] text-[#334155] hover:bg-[#f8fafc]"
      }`}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" />}
      {label}
    </button>
  );
}

function ValidationPanel({ artifacts, busy, onValidate }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const report = artifacts?.validation;
  const passed = report?.status === "passed";
  return (
    <div className="rounded-lg border border-[#d9dee7] bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <CheckCircle2 className={`mt-0.5 h-5 w-5 ${passed ? "text-[#16a34a]" : "text-[#64748b]"}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#111827]">Validation report</p>
          <p className="mt-1 text-sm leading-6 text-[#475569]">
            Run install, type-check/test, and build scripts for the generated MVP.
          </p>
        </div>
      </div>
      <button
        type="button"
        disabled={!hasFiles || busy}
        onClick={onValidate}
        className="mt-4 inline-flex w-full min-h-10 items-center justify-center gap-2 rounded-md bg-[#2563eb] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1d4ed8] disabled:cursor-not-allowed disabled:bg-[#94a3b8]"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
        Validate generated app
      </button>
      {report && (
        <div className="mt-4">
          <StatusPill status={report.status} />
          <div className="mt-3 flex flex-col gap-2">
            {(report.checks || []).map((check) => (
              <div key={check.name} className="rounded-md border border-[#e5e7eb] px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-[#111827]">{check.name}</span>
                  <span className={check.returncode === 0 ? "text-[#15803d]" : "text-[#b91c1c]"}>
                    exit {check.returncode}
                  </span>
                </div>
                <p className="mt-1 text-[#64748b]">{check.duration_seconds}s</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QualityPanel({ artifacts, busy, onCheck }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const report = artifacts?.quality;
  const accepted = report?.status === "accepted" || report?.status === "target_met";
  return (
    <div className="rounded-lg border border-[#d9dee7] bg-white p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <Sparkles className={`mt-0.5 h-5 w-5 ${accepted ? "text-[#16a34a]" : "text-[#7c3aed]"}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[#111827]">10/10 quality gate</p>
          <p className="mt-1 text-sm leading-6 text-[#475569]">
            Score the generated app before presenting it as the final SWARM output.
          </p>
        </div>
      </div>
      <button
        type="button"
        disabled={!hasFiles || busy}
        onClick={onCheck}
        className="mt-4 inline-flex w-full min-h-10 items-center justify-center gap-2 rounded-md bg-[#7c3aed] px-4 py-2 text-sm font-semibold text-white hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:bg-[#94a3b8]"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        Run quality gate
      </button>
      {report && (
        <div className="mt-4">
          <div className="grid grid-cols-2 gap-2">
            <Info label="Score" value={`${report.score}/100`} />
            <Info label="Grade" value={report.grade} />
            <Info label="Accepts at" value={report.minimum_score ?? 90} />
            <Info label="10/10 target" value={report.target_score ?? 90} />
          </div>
          <div className="mt-3">
            <StatusPill status={report.status} />
          </div>
          {(report.revision_instructions || []).length > 0 && (
            <div className="mt-3 rounded-md border border-[#ede9fe] bg-[#faf5ff] p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6d28d9]">Top fixes</p>
              <div className="mt-2 flex flex-col gap-1">
                {report.revision_instructions.slice(0, 4).map((item) => (
                  <p key={item} className="text-xs leading-5 text-[#4c1d95]">{item}</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Overview({ output, artifacts, runId }) {
  if (!output && !artifacts) return <EmptyState title="No artifacts yet" text="Start a run to generate product, architecture, code, and pitch output." />;
  const counts = artifacts?.artifact_counts || {};
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SummaryBlock title="Problem" value={output?.requirements?.problem_statement} />
      <SummaryBlock title="Target Audience" value={output?.requirements?.target_audience} />
      <div className="rounded-lg border border-[#e5e7eb] p-4">
        <p className="text-sm font-semibold text-[#111827]">Artifact package</p>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <Info label="Code files" value={counts.code_files ?? 0} />
          <Info label="Pitch fields" value={counts.pitch_deck_fields ?? 0} />
          <Info label="Dependencies" value={artifacts?.detected_app?.dependencies?.length ?? 0} />
          <Info label="Dev deps" value={artifacts?.detected_app?.dev_dependencies?.length ?? 0} />
        </div>
      </div>
      <div className="rounded-lg border border-[#e5e7eb] p-4">
        <p className="text-sm font-semibold text-[#111827]">Demo actions</p>
        <div className="mt-4 flex flex-col gap-2">
          <a className="inline-flex items-center gap-2 text-sm font-semibold text-[#2563eb]" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
            Open API docs <ArrowUpRight className="h-4 w-4" />
          </a>
          {runId && (artifacts?.artifact_counts?.code_files ?? 0) > 0 && (
            <a className="inline-flex items-center gap-2 text-sm font-semibold text-[#2563eb]" href={`${API_BASE_URL}/download/${runId}`}>
              Download generated app <Download className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function DemoMode({ demo, preview, runId }) {
  if (!demo) {
    return (
      <EmptyState
        title="Demo story pending"
        text="Complete a run to generate the judge-facing mission control summary."
      />
    );
  }

  const validationPassed = demo.delivery?.validation_status === "passed";
  const qualityStrong = (demo.delivery?.quality_score ?? 0) >= 82;
  const agents = Object.entries(demo.status?.agent_statuses || {});

  return (
    <div className="grid gap-5">
      <div className="rounded-xl bg-[#0f172a] p-6 text-white">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#93c5fd]">Demo Mode</p>
            <h2 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight">
              {demo.story?.tagline || "Local business workflow transformed into a validated, runnable app."}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[#cbd5e1]">{demo.idea}</p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5 lg:min-w-[620px]">
            <DemoMetric label="Agents" value={`${agents.filter(([, value]) => value === "done").length}/4`} />
            <DemoMetric label="Files" value={demo.delivery?.code_file_count ?? 0} />
            <DemoMetric label="Validation" value={demo.delivery?.validation_status || "not run"} good={validationPassed} />
            <DemoMetric label="Quality" value={demo.delivery?.quality_score ? `${demo.delivery.quality_score}/100` : "not run"} good={qualityStrong} />
            <DemoMetric label="Status" value={demo.status?.done ? "complete" : "running"} good={demo.status?.done} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <NarrativeCard title="Problem" text={demo.story?.problem} />
        <NarrativeCard title="Audience" text={demo.story?.audience} />
        <NarrativeCard title="Solution" text={demo.story?.solution} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-lg border border-[#e5e7eb] p-5">
          <p className="text-sm font-semibold text-[#111827]">Agent execution chain</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {STEPS.map((step, index) => {
              const status = demo.status?.agent_statuses?.[step.id] || "pending";
              const Icon = step.icon;
              return (
                <div key={step.id} className="rounded-lg border border-[#e5e7eb] bg-[#f8fafc] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-9 w-9 items-center justify-center rounded-md ${stepColor(status)}`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-[#111827]">{step.label}</p>
                        <p className="text-xs text-[#64748b]">Step {index + 1}</p>
                      </div>
                    </div>
                    <StatusPill status={status} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-lg border border-[#e5e7eb] p-5">
          <p className="text-sm font-semibold text-[#111827]">Generated MVP</p>
          <div className="mt-4 flex flex-col gap-3">
            <SummaryRow label="App" value={demo.delivery?.app_name || "Generated app"} />
            <SummaryRow label="Files" value={demo.delivery?.code_file_count ?? 0} />
            <SummaryRow label="Validation" value={demo.delivery?.validation_status || "not run"} />
            <SummaryRow label="Quality" value={demo.delivery?.quality_grade || "not run"} />
            <SummaryRow label="Preview" value={preview?.running ? preview.frontend_url : "Not running"} />
          </div>
          {preview?.running && (
            <a
              href={preview.frontend_url}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-[#16a34a] px-4 py-2 text-sm font-semibold text-white hover:bg-[#15803d]"
            >
              Open live MVP <ArrowUpRight className="h-4 w-4" />
            </a>
          )}
          {runId && (
            <a
              href={`${API_BASE_URL}/download/${runId}`}
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-md border border-[#cbd5e1] px-4 py-2 text-sm font-semibold text-[#334155] hover:bg-[#f8fafc]"
            >
              Download package <Download className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <ListBlock title="MVP Features" items={demo.product?.features || []} />
        <div className="rounded-lg border border-[#e5e7eb] p-5">
          <p className="text-sm font-semibold text-[#111827]">Investor close</p>
          <p className="mt-3 text-sm leading-7 text-[#475569]">{demo.story?.call_to_action || "Pitch deck pending."}</p>
        </div>
      </div>
    </div>
  );
}

function DemoMetric({ label, value, good }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/10 p-3">
      <p className="text-xs uppercase tracking-[0.12em] text-[#93c5fd]">{label}</p>
      <p className={`mt-1 truncate text-lg font-semibold ${good ? "text-[#86efac]" : "text-white"}`}>{String(value)}</p>
    </div>
  );
}

function NarrativeCard({ title, text }) {
  return (
    <div className="rounded-lg border border-[#e5e7eb] p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#2563eb]">{title}</p>
      <p className="mt-3 text-sm leading-7 text-[#475569]">{text || "Pending"}</p>
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-[#f1f5f9] pb-2 text-sm">
      <span className="text-[#64748b]">{label}</span>
      <span className="truncate font-semibold text-[#111827]">{String(value)}</span>
    </div>
  );
}

function SummaryBlock({ title, value }) {
  return (
    <div className="rounded-lg border border-[#e5e7eb] p-4">
      <p className="text-sm font-semibold text-[#111827]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[#475569]">{value || "Pending"}</p>
    </div>
  );
}

function Requirements({ requirements }) {
  if (!requirements || !Object.keys(requirements).length) return <EmptyState title="Requirements pending" text="The Analyst agent will turn the idea into MVP requirements." />;
  return (
    <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
      <SummaryBlock title="Problem Statement" value={requirements.problem_statement} />
      <SummaryBlock title="Target Audience" value={requirements.target_audience} />
      <ListBlock title="Core Features" items={requirements.core_features} />
      <ListBlock title="Success Metrics" items={requirements.success_metrics} />
      <ListBlock title="User Stories" items={requirements.user_stories} wide />
    </div>
  );
}

function Architecture({ architecture }) {
  if (!architecture || !Object.keys(architecture).length) return <EmptyState title="Architecture pending" text="The Architect agent will produce stack, schema, API, and module plans." />;
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(architecture.tech_stack || {}).map(([key, value]) => (
          <SummaryBlock key={key} title={key.replaceAll("_", " ")} value={String(value)} />
        ))}
      </div>
      <ListBlock title="API Routes" items={(architecture.api_routes || []).map((route) => `${route.method} ${route.path} - ${route.description}`)} />
      <JsonPanel title="Database Schema" data={architecture.database_schema} />
      <JsonPanel title="Folder Structure" data={architecture.folder_structure} language="text" />
    </div>
  );
}

function CodeExplorer({ files, selectedFile, selectedFileContent, onSelect }) {
  const paths = Object.keys(files || {}).sort();
  if (!paths.length) return <EmptyState title="Code pending" text="When SWARM Builder finishes, the generated project appears here." />;
  return (
    <div className="grid min-h-[560px] gap-4 lg:grid-cols-[290px_minmax(0,1fr)]">
      <div className="overflow-hidden rounded-lg border border-[#e5e7eb]">
        <div className="border-b border-[#e5e7eb] px-3 py-2 text-sm font-semibold">Files</div>
        <div className="max-h-[520px] overflow-auto">
          {paths.map((path) => (
            <button
              key={path}
              type="button"
              onClick={() => onSelect(path)}
              className={`flex w-full items-center gap-2 border-b border-[#f1f5f9] px-3 py-2 text-left text-xs ${
                selectedFile === path ? "bg-[#eff6ff] text-[#1d4ed8]" : "text-[#475569] hover:bg-[#f8fafc]"
              }`}
            >
              <FileCode2 className="h-3.5 w-3.5 shrink-0" />
              <span className="break-all font-mono">{path}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="min-w-0 overflow-hidden rounded-lg border border-[#e5e7eb]">
        <div className="border-b border-[#e5e7eb] px-3 py-2 font-mono text-xs text-[#475569]">{selectedFile}</div>
        <SyntaxHighlighter language={languageForPath(selectedFile)} style={oneLight} customStyle={codeStyle}>
          {selectedFileContent || ""}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

function PitchDeck({ deck }) {
  if (!deck || !Object.keys(deck).length) return <EmptyState title="Pitch pending" text="Pitch Strategist runs after SWARM Builder creates the generated app." />;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {Object.entries(deck).map(([key, value]) => (
        <div key={key} className="rounded-lg border border-[#e5e7eb] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#2563eb]">{key.replaceAll("_", " ")}</p>
          <p className="mt-2 text-sm leading-6 text-[#334155]">{Array.isArray(value) ? value.join(", ") : String(value)}</p>
        </div>
      ))}
    </div>
  );
}

function ListBlock({ title, items = [], wide = false }) {
  return (
    <div className={`rounded-lg border border-[#e5e7eb] p-4 ${wide ? "lg:col-span-2" : ""}`}>
      <p className="text-sm font-semibold text-[#111827]">{title}</p>
      <div className="mt-3 flex flex-col gap-2">
        {items?.length ? (
          items.map((item) => (
            <div key={item} className="flex gap-2 text-sm leading-6 text-[#475569]">
              <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-[#16a34a]" />
              <span>{item}</span>
            </div>
          ))
        ) : (
          <p className="text-sm text-[#64748b]">Pending</p>
        )}
      </div>
    </div>
  );
}

function JsonPanel({ title, data, language = "json" }) {
  const content = typeof data === "string" ? data : JSON.stringify(data || {}, null, 2);
  return (
    <div className="overflow-hidden rounded-lg border border-[#e5e7eb]">
      <div className="border-b border-[#e5e7eb] px-4 py-3 text-sm font-semibold">{title}</div>
      <SyntaxHighlighter language={language} style={oneLight} customStyle={codeStyle}>
        {content}
      </SyntaxHighlighter>
    </div>
  );
}

function EmptyState({ title, text }) {
  return (
    <div className="flex min-h-[360px] flex-col items-center justify-center rounded-lg border border-dashed border-[#cbd5e1] bg-[#f8fafc] px-6 text-center">
      <Play className="h-8 w-8 text-[#64748b]" />
      <p className="mt-3 text-base font-semibold text-[#111827]">{title}</p>
      <p className="mt-1 max-w-md text-sm leading-6 text-[#64748b]">{text}</p>
    </div>
  );
}

function StatusPill({ status }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${pillColor(status)}`}>{status.replaceAll("_", " ")}</span>;
}

function stepColor(status) {
  if (status === "done") return "bg-[#dcfce7] text-[#166534]";
  if (status === "running") return "bg-[#dbeafe] text-[#1d4ed8]";
  if (status === "waiting_for_trae") return "bg-[#fef3c7] text-[#92400e]";
  if (status === "error") return "bg-[#fee2e2] text-[#991b1b]";
  return "bg-[#f1f5f9] text-[#64748b]";
}

function pillColor(status) {
  if (status === "done" || status === "Complete" || status === "passed") return "bg-[#dcfce7] text-[#166534]";
  if (status === "target_met") return "bg-[#dcfce7] text-[#166534]";
  if (status === "accepted") return "bg-[#dcfce7] text-[#166534]";
  if (status === "needs_revision") return "bg-[#fef3c7] text-[#92400e]";
  if (status === "failed") return "bg-[#fee2e2] text-[#991b1b]";
  if (status === "builder") return "bg-[#fef3c7] text-[#92400e]";
  if (status === "idle") return "bg-[#f1f5f9] text-[#475569]";
  return "bg-[#dbeafe] text-[#1d4ed8]";
}

function languageForPath(path = "") {
  const extension = path.split(".").pop();
  const map = {
    css: "css",
    html: "html",
    js: "javascript",
    json: "json",
    jsx: "jsx",
    md: "markdown",
    py: "python",
    sql: "sql",
    ts: "typescript",
    tsx: "tsx",
  };
  return map[extension] || "text";
}

function formatTime(value) {
  if (!value) return "Pending";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const codeStyle = {
  margin: 0,
  minHeight: "520px",
  maxHeight: "620px",
  overflow: "auto",
  background: "#fbfdff",
  fontSize: "0.82rem",
};
