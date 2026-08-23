import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircuitBoard,
  Code2,
  Download,
  ExternalLink,
  FileCode2,
  Layers3,
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  Rocket,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import blackHoleReference from "./assets/blackhole-reference.webp";
import blackHoleMotion from "./assets/black-hole-motion.mp4";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const STEPS = [
  { id: "analyst", label: "Product Analyst", icon: BrainCircuit, activeText: "Extracting product intent" },
  { id: "architect", label: "Software Architect", icon: CircuitBoard, activeText: "Shaping system plan" },
  { id: "builder", label: "SWARM Builder", icon: Code2, activeText: "Generating application code" },
  { id: "openhands", label: "OpenHands Builder", icon: Bot, activeText: "Hardening implementation" },
  { id: "pitcher", label: "Pitch Strategist", icon: Layers3, activeText: "Packaging the story" },
];

const TABS = [
  ["demo", "Demo"],
  ["overview", "Overview"],
  ["requirements", "Requirements"],
  ["architecture", "Architecture"],
  ["code", "Code"],
  ["preview", "Preview"],
  ["pitch", "Pitch"],
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
  const presentation = useMemo(
    () => buildPresentationState({ runId, status, artifacts, preview, validationBusy, qualityBusy, isStarting, error }),
    [runId, status, artifacts, preview, validationBusy, qualityBusy, isStarting, error],
  );

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
    <main className="swarm-workspace">
      <BlackHoleBackdrop />
      <header className="home-nav">
        <div className="home-brand"><span className="brand-orbit" />SWARM</div>
        <nav>
          <a href={`${API_BASE_URL}/runs`} target="_blank" rel="noreferrer">Runs</a>
          <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">API</a>
          <span className={`system-chip ${presentation.tone}`}>{presentation.systemStatus}</span>
        </nav>
      </header>

      <section className="home-composer" aria-label="Start a SWARM run">
        <p className="home-kicker">SWARM.AI</p>
        <h1>What will you build?</h1>
        <p className="home-subtitle">Describe the product. Your agents will turn it into a working application.</p>
        <form onSubmit={startRun} className="home-form">
          <div className="mode-tabs" aria-hidden="true"><span className="is-selected">Web app</span><span>Product build</span></div>
          <label className="sr-only" htmlFor="idea">Describe your product idea</label>
          <textarea id="idea" rows={5} value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="Describe the product you want to create..." />
          <div className="composer-actions">
            <button type="button" className="icon-button" aria-label="Use example" title="Use example" onClick={() => setIdea(SAMPLE_IDEA)}><Plus className="h-5 w-5" /></button>
            <span>{presentation.metadata.label}</span>
            <button type="submit" className="submit-button" disabled={!idea.trim() || isStarting} aria-label="Build application" title="Build application">
              {isStarting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Rocket className="h-5 w-5" />}
            </button>
          </div>
        </form>
        <p className="suggestion-label">Start with one of these</p>
        <div className="suggestion-list">
          {["Client portal for a services business", "Marketplace for a niche community", "Operations dashboard for a growing team"].map((item) => (
            <button key={item} type="button" onClick={() => setIdea(item)}><i />{item}</button>
          ))}
        </div>
        {error && <ErrorBanner message={error} />}
      </section>

      {runId && (
        <section className="run-workspace">
          <div className="run-strip"><RunStatusBar metadata={presentation.metadata} /><RunPanel runId={runId} status={status} artifacts={artifacts} /></div>
          <AgentPipeline status={status} />
          <section className="output-shell">
            <div className="output-tabs" role="tablist" aria-label="Generated output">
              {TABS.map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={activeTab === id} onClick={() => setActiveTab(id)} className={`tab-button ${activeTab === id ? "is-active" : ""}`}>{label}</button>)}
            </div>
            <div className="output-content">
              {activeTab === "demo" && <DemoMode demo={demo} preview={preview} runId={runId} />}
              {activeTab === "overview" && <Overview output={output} artifacts={artifacts} runId={runId} />}
              {activeTab === "requirements" && <Requirements requirements={output?.requirements} />}
              {activeTab === "architecture" && <Architecture architecture={output?.architecture} />}
              {activeTab === "code" && <CodeExplorer files={codeFiles} selectedFile={selectedFile} selectedFileContent={selectedFileContent} onSelect={setSelectedFile} />}
              {activeTab === "preview" && <PreviewWorkspace runId={runId} artifacts={artifacts} preview={preview} busy={previewBusy} onAction={runPreviewAction} />}
              {activeTab === "pitch" && <PitchDeck deck={output?.pitch_deck} />}
            </div>
          </section>
        </section>
      )}
    </main>
  );
}

function BlackHoleBackdrop() {
  return (
    <div className="black-hole-backdrop" aria-hidden="true">
      <video className="black-hole-motion" autoPlay loop muted playsInline poster={blackHoleReference}>
        <source src={blackHoleMotion} type="video/mp4" />
      </video>
      <span className="backdrop-glow" />
    </div>
  );
}

function TopNav({ presentation }) {
  return (
    <header className="top-nav">
      <div className="brand-mark" aria-label="SWARM.AI">
        <span className="brand-orbit" />
        <span>SWARM</span>
      </div>
      <nav className="top-nav-actions" aria-label="Workspace">
        <a href={`${API_BASE_URL}/runs`} target="_blank" rel="noreferrer">
          Runs
        </a>
        <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
          API
        </a>
        <span className={`system-chip ${presentation.tone}`}>{presentation.systemStatus}</span>
      </nav>
    </header>
  );
}

function PromptComposer({ idea, isStarting, metadata, onIdeaChange, onLoadExample, onSubmit }) {
  return (
    <section className="prompt-shell">
      <div className="prompt-copy">
        <p className="eyebrow">SWARM</p>
        <h1>Turn ideas into working software.</h1>
      </div>
      <form onSubmit={onSubmit} className="prompt-form">
        <label className="sr-only" htmlFor="idea">
          Describe what you want to build
        </label>
        <textarea
          id="idea"
          rows={4}
          value={idea}
          onChange={(event) => onIdeaChange(event.target.value)}
          placeholder="Describe what you want to build..."
          className="idea-input"
        />
        <div className="prompt-actions">
          <button type="button" onClick={onLoadExample} className="secondary-button">
            <Sparkles className="h-4 w-4" />
            Example
          </button>
          <button type="submit" disabled={!idea.trim() || isStarting} className="primary-button">
            {isStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
            Generate
          </button>
        </div>
      </form>
      <RunStatusBar metadata={metadata} />
    </section>
  );
}

function RunStatusBar({ metadata }) {
  return (
    <div className="run-status" aria-live="polite">
      <span className={`status-dot ${metadata.tone}`} />
      <span>{metadata.label}</span>
      {metadata.items.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </div>
  );
}

function ErrorBanner({ message }) {
  return (
    <div className="error-banner" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function RunPanel({ runId, status, artifacts }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  return (
    <section className="panel compact-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Run</p>
          <p className="run-id">{runId || "No active run"}</p>
        </div>
        <StatusBadge status={status?.done ? "done" : status?.current_agent || "idle"} />
      </div>
      <div className="mini-grid">
        <Info label="Updated" value={formatTime(status?.updated_at)} />
        <Info label="App" value={artifacts?.detected_app?.name || "Pending"} />
      </div>
      {runId && hasFiles && (
        <a href={`${API_BASE_URL}/download/${runId}`} className="quiet-action">
          <Download className="h-4 w-4" />
          Download zip
        </a>
      )}
    </section>
  );
}

function AgentPipeline({ status }) {
  const statuses = status?.agent_statuses || {};
  return (
    <section className="panel">
      <div className="panel-heading">
        <p className="panel-title">Pipeline</p>
        <span className="panel-meta">{status?.done ? "Complete" : status?.current_agent || "Ready"}</span>
      </div>
      <div className="pipeline-list">
        {STEPS.map((step) => {
          const stepStatus = statuses[step.id] || "pending";
          return <AgentPipelineItem key={step.id} step={step} status={stepStatus} active={stepStatus === "running"} />;
        })}
      </div>
      {(status?.errors || []).length > 0 && (
        <details className="details-block">
          <summary>Errors</summary>
          <div className="details-stack">
            {status.errors.map((message) => (
              <p key={message}>{message}</p>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function AgentPipelineItem({ step, status, active }) {
  const Icon = step.icon;
  return (
    <div className={`pipeline-item ${pipelineClass(status)}`}>
      <div className="pipeline-node" aria-label={`${step.label} ${status.replaceAll("_", " ")}`}>
        {status === "running" ? <Loader2 className="h-4 w-4 animate-spin" /> : status === "done" ? <CheckCircle2 className="h-4 w-4" /> : status === "error" ? <AlertTriangle className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
      </div>
      <div className="min-w-0">
        <p>{step.label}</p>
        {active && <span>{step.activeText}</span>}
        {status === "waiting_for_trae" && <span>Awaiting revision workflow</span>}
      </div>
    </div>
  );
}

function MissionControl({ presentation, runId, preview, artifacts }) {
  const appName = artifacts?.detected_app?.name || "Generated app";
  return (
    <div className="mission-control">
      <BlackHoleScene visualState={presentation.blackHole} />
      <div className="mission-overlay">
        <div>
          <p className="mission-state">{presentation.blackHole.label}</p>
          <p className="mission-agent">{presentation.blackHole.agentLabel}</p>
        </div>
        {presentation.blackHole.phase === "complete" && (
          <div className="completion-card">
            <p>Complete</p>
            <strong>{appName}</strong>
            <div className="completion-actions">
              {preview?.running && (
                <a href={preview.frontend_url} target="_blank" rel="noreferrer" className="primary-link">
                  Open App <ArrowUpRight className="h-4 w-4" />
                </a>
              )}
              {runId && (
                <a href={`${API_BASE_URL}/download/${runId}`} className="secondary-link">
                  Download
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function BlackHoleScene({ visualState }) {
  return (
    <div
      className={`black-hole-stage phase-${visualState.phase}`}
      style={{
        "--rotation-speed": `${visualState.rotation}s`,
        "--disk-opacity": visualState.disk,
        "--halo-opacity": visualState.halo,
        "--star-distance": `${visualState.starDistance}px`,
        "--star-scale": visualState.starScale,
        "--stream-opacity": visualState.stream,
        "--jet-opacity": visualState.jet,
        "--scan-opacity": visualState.scan,
      }}
      aria-hidden="true"
    >
      <div className="starfield" />
      <div className="black-hole-core">
        <img src={blackHoleImage} alt="" className="black-hole-asset" />
        <span className="event-horizon" />
        <span className="accretion accretion-one" />
        <span className="accretion accretion-two" />
        <span className="halo-ring" />
        <span className="scan-ring" />
        <span className="completion-jet" />
      </div>
      <span className="idea-star" />
      <span className="tidal-stream" />
      <div className="particle-field">
        {Array.from({ length: 18 }, (_, index) => (
          <span key={index} style={{ "--i": index }} />
        ))}
      </div>
    </div>
  );
}

function PreviewPanel({ runId, artifacts, preview, busy, onAction }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const mainAction = getPreviewMainAction({ runId, hasFiles, preview });
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="panel-title">App Preview</p>
          <p className="panel-meta">{previewStatusLabel(preview, hasFiles)}</p>
        </div>
        <span className={`live-dot ${preview?.running ? "on" : ""}`} />
      </div>

      <button
        type="button"
        disabled={!mainAction || Boolean(busy)}
        onClick={() => mainAction && onAction(mainAction.action)}
        className="primary-button full-width"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : mainAction?.icon || <Play className="h-4 w-4" />}
        {busy ? actionLabel(busy) : mainAction?.label || "Prepare"}
      </button>

      {preview?.frontend_url && preview?.running && (
        <a href={preview.frontend_url} target="_blank" rel="noreferrer" className="quiet-action">
          <ExternalLink className="h-4 w-4" />
          {preview.frontend_url}
        </a>
      )}

      <details className="details-block">
        <summary>
          <MoreHorizontal className="h-4 w-4" />
          Runtime
        </summary>
        <div className="runtime-menu">
          {["prepare", "install", "start", "launch", "stop"].map((action) => (
            <button
              key={action}
              type="button"
              disabled={previewActionDisabled(action, { runId, hasFiles, preview, busy })}
              onClick={() => onAction(action)}
            >
              {busy === action && <Loader2 className="h-4 w-4 animate-spin" />}
              {actionLabel(action)}
            </button>
          ))}
        </div>
        <div className="mini-grid">
          <Info label="Prepared" value={preview?.prepared ? "Yes" : "No"} />
          <Info label="Installed" value={preview?.dependencies_installed ? "Yes" : "No"} />
          <Info label="Client" value={preview?.client_running ? "Running" : "Stopped"} />
          <Info label="Server" value={preview?.server_running ? "Running" : "Stopped"} />
        </div>
        {preview?.api_url && (
          <a className="mono-link" href={`${preview.api_url}/api/health`} target="_blank" rel="noreferrer">
            {preview.api_url}/api/health
          </a>
        )}
        {preview?.log_dir && <p className="log-path">Logs: {preview.log_dir}</p>}
        <LogDetails preview={preview} />
      </details>
    </section>
  );
}

function PreviewWorkspace(props) {
  return (
    <div className="workspace-grid">
      <PreviewPanel {...props} />
      <div className="panel">
        <p className="panel-title">Runtime Information</p>
        <JsonPanel title="Preview Status" data={props.preview || { status: "No preview created" }} />
      </div>
    </div>
  );
}

function ValidationPanel({ artifacts, busy, onValidate }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const report = artifacts?.validation;
  const checks = report?.checks || [];
  const passed = report?.status === "passed";
  const passedCount = checks.filter((check) => check.returncode === 0).length;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="panel-title">Validation</p>
          <p className="panel-meta">{report ? `${passedCount}/${checks.length} checks` : "Ready"}</p>
        </div>
        <StatusBadge status={report?.status || "idle"} />
      </div>
      <button type="button" disabled={!hasFiles || busy} onClick={onValidate} className="secondary-button full-width">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
        Validate
      </button>
      {report && (
        <details className="details-block">
          <summary>Report</summary>
          <div className="check-list">
            {checks.map((check) => (
              <div key={check.name} className="check-row">
                <span>{check.returncode === 0 ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}</span>
                <strong>{check.name}</strong>
                <em>{check.duration_seconds}s</em>
              </div>
            ))}
          </div>
          <JsonPanel title="Raw validation" data={report} />
        </details>
      )}
    </section>
  );
}

function QualityPanel({ artifacts, busy, onCheck }) {
  const hasFiles = (artifacts?.artifact_counts?.code_files ?? 0) > 0;
  const report = artifacts?.quality;
  const accepted = report?.status === "accepted" || report?.status === "target_met";
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="panel-title">Quality</p>
          <p className="panel-meta">{report ? `${report.score}/100 ${report.grade || ""}` : "Not evaluated"}</p>
        </div>
        <StatusBadge status={accepted ? "passed" : report?.status || "idle"} />
      </div>
      <button type="button" disabled={!hasFiles || busy} onClick={onCheck} className="secondary-button full-width violet">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        Evaluate
      </button>
      {report && (
        <details className="details-block">
          <summary>Evaluation</summary>
          <div className="mini-grid">
            <Info label="Score" value={`${report.score}/100`} />
            <Info label="Grade" value={report.grade} />
            <Info label="Accepts at" value={report.minimum_score ?? 90} />
            <Info label="Target" value={report.target_score ?? 90} />
          </div>
          {(report.revision_instructions || []).length > 0 && <ListBlock title="Top Fixes" items={report.revision_instructions.slice(0, 4)} />}
          <JsonPanel title="Raw evaluation" data={report} />
        </details>
      )}
    </section>
  );
}

function Overview({ output, artifacts, runId }) {
  if (!output && !artifacts) return <EmptyState title="Ready" text="Waiting for generated artifacts." />;
  const counts = artifacts?.artifact_counts || {};
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SummaryBlock title="Problem" value={output?.requirements?.problem_statement} />
      <SummaryBlock title="Audience" value={output?.requirements?.target_audience} />
      <div className="panel">
        <p className="panel-title">Artifacts</p>
        <div className="mini-grid">
          <Info label="Code files" value={counts.code_files ?? 0} />
          <Info label="Pitch fields" value={counts.pitch_deck_fields ?? 0} />
          <Info label="Dependencies" value={artifacts?.detected_app?.dependencies?.length ?? 0} />
          <Info label="Dev deps" value={artifacts?.detected_app?.dev_dependencies?.length ?? 0} />
        </div>
      </div>
      <div className="panel">
        <p className="panel-title">Actions</p>
        <div className="action-stack">
          <a className="quiet-action" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
            <ArrowUpRight className="h-4 w-4" />
            API docs
          </a>
          {runId && (artifacts?.artifact_counts?.code_files ?? 0) > 0 && (
            <a className="quiet-action" href={`${API_BASE_URL}/download/${runId}`}>
              <Download className="h-4 w-4" />
              Download app
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function DemoMode({ demo, preview, runId }) {
  if (!demo) return <EmptyState title="Ready" text="Demo story appears after a completed run." />;

  const validationPassed = demo.delivery?.validation_status === "passed";
  const qualityStrong = (demo.delivery?.quality_score ?? 0) >= 82;
  const agents = Object.entries(demo.status?.agent_statuses || {});

  return (
    <div className="grid gap-5">
      <div className="demo-hero">
        <div>
          <p className="eyebrow">Demo</p>
          <h2>{demo.story?.tagline || "Generated MVP ready for review."}</h2>
          <p>{demo.idea}</p>
        </div>
        <div className="demo-metrics">
          <DemoMetric label="Agents" value={`${agents.filter(([, value]) => value === "done").length}/5`} />
          <DemoMetric label="Files" value={demo.delivery?.code_file_count ?? 0} />
          <DemoMetric label="Validation" value={demo.delivery?.validation_status || "not run"} good={validationPassed} />
          <DemoMetric label="Quality" value={demo.delivery?.quality_score ? `${demo.delivery.quality_score}/100` : "not run"} good={qualityStrong} />
          <DemoMetric label="Status" value={demo.status?.done ? "complete" : "running"} good={demo.status?.done} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <NarrativeCard title="Problem" text={demo.story?.problem} />
        <NarrativeCard title="Audience" text={demo.story?.audience} />
        <NarrativeCard title="Solution" text={demo.story?.solution} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <ListBlock title="MVP Features" items={demo.product?.features || []} />
        <div className="panel">
          <p className="panel-title">Generated MVP</p>
          <div className="summary-stack">
            <SummaryRow label="App" value={demo.delivery?.app_name || "Generated app"} />
            <SummaryRow label="Files" value={demo.delivery?.code_file_count ?? 0} />
            <SummaryRow label="Validation" value={demo.delivery?.validation_status || "not run"} />
            <SummaryRow label="Quality" value={demo.delivery?.quality_grade || "not run"} />
            <SummaryRow label="Preview" value={preview?.running ? preview.frontend_url : "Not running"} />
          </div>
          <div className="action-stack">
            {preview?.running && (
              <a href={preview.frontend_url} target="_blank" rel="noreferrer" className="primary-link">
                Open live MVP <ArrowUpRight className="h-4 w-4" />
              </a>
            )}
            {runId && (
              <a href={`${API_BASE_URL}/download/${runId}`} className="quiet-action">
                <Download className="h-4 w-4" />
                Download package
              </a>
            )}
          </div>
        </div>
      </div>

      <details className="details-block panel">
        <summary>Pitch Close</summary>
        <p className="body-copy">{demo.story?.call_to_action || "Pitch deck pending."}</p>
      </details>
    </div>
  );
}

function Requirements({ requirements }) {
  if (!requirements || !Object.keys(requirements).length) return <EmptyState title="Requirements pending" text="Analyst output will appear here." />;
  return (
    <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
      <SummaryBlock title="Problem" value={requirements.problem_statement} />
      <SummaryBlock title="Audience" value={requirements.target_audience} />
      <ListBlock title="Core Features" items={requirements.core_features} />
      <ListBlock title="Success Metrics" items={requirements.success_metrics} />
      <ListBlock title="User Stories" items={requirements.user_stories} wide />
    </div>
  );
}

function Architecture({ architecture }) {
  if (!architecture || !Object.keys(architecture).length) return <EmptyState title="Architecture pending" text="System plan will appear here." />;
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
  if (!paths.length) return <EmptyState title="Code pending" text="Generated project files appear here." />;
  return (
    <div className="code-grid">
      <div className="file-list">
        <div className="file-list-title">Files</div>
        <div>
          {paths.map((path) => (
            <button key={path} type="button" onClick={() => onSelect(path)} className={`file-button ${selectedFile === path ? "is-active" : ""}`}>
              <FileCode2 className="h-3.5 w-3.5 shrink-0" />
              <span>{path}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="code-panel">
        <div className="code-title">{selectedFile}</div>
        <SyntaxHighlighter language={languageForPath(selectedFile)} style={oneLight} customStyle={codeStyle}>
          {selectedFileContent || ""}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

function PitchDeck({ deck }) {
  if (!deck || !Object.keys(deck).length) return <EmptyState title="Pitch pending" text="Pitch Strategist output will appear here." />;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {Object.entries(deck).map(([key, value]) => (
        <SummaryBlock key={key} title={key.replaceAll("_", " ")} value={Array.isArray(value) ? value.join(", ") : String(value)} />
      ))}
    </div>
  );
}

function LogDetails({ preview }) {
  const records = [
    ["Install", preview?.last_install],
    ["Build", preview?.last_build],
    ["Schema", preview?.last_schema_setup],
    ["Start error", preview?.last_start_error],
    ["Probe", preview?.last_probe],
  ].filter(([, value]) => value);
  if (!records.length) return null;
  return (
    <details className="details-block nested">
      <summary>
        <TerminalSquare className="h-4 w-4" />
        Logs
      </summary>
      {records.map(([label, value]) => (
        <JsonPanel key={label} title={label} data={value} />
      ))}
    </details>
  );
}

function Info({ label, value }) {
  return (
    <div className="info-cell">
      <p>{label}</p>
      <strong>{value ?? "Pending"}</strong>
    </div>
  );
}

function DemoMetric({ label, value, good }) {
  return (
    <div className={`demo-metric ${good ? "good" : ""}`}>
      <p>{label}</p>
      <strong>{String(value)}</strong>
    </div>
  );
}

function NarrativeCard({ title, text }) {
  return <SummaryBlock title={title} value={text || "Pending"} />;
}

function SummaryRow({ label, value }) {
  return (
    <div className="summary-row">
      <span>{label}</span>
      <strong>{String(value)}</strong>
    </div>
  );
}

function SummaryBlock({ title, value }) {
  return (
    <div className="panel summary-block">
      <p className="panel-title">{title}</p>
      <p className="body-copy">{value || "Pending"}</p>
    </div>
  );
}

function ListBlock({ title, items = [], wide = false }) {
  return (
    <div className={`panel list-block ${wide ? "lg:col-span-2" : ""}`}>
      <p className="panel-title">{title}</p>
      <div className="list-stack">
        {items?.length ? (
          items.map((item) => (
            <div key={item} className="list-item">
              <CheckCircle2 className="mt-1 h-4 w-4 shrink-0" />
              <span>{item}</span>
            </div>
          ))
        ) : (
          <p className="body-copy">Pending</p>
        )}
      </div>
    </div>
  );
}

function JsonPanel({ title, data, language = "json" }) {
  const content = typeof data === "string" ? data : JSON.stringify(data || {}, null, 2);
  return (
    <div className="json-panel">
      <div className="json-title">{title}</div>
      <SyntaxHighlighter language={language} style={oneLight} customStyle={codeStyle}>
        {content}
      </SyntaxHighlighter>
    </div>
  );
}

function EmptyState({ title, text }) {
  return (
    <div className="empty-state">
      <div className="empty-orbit">
        <Play className="h-7 w-7" />
      </div>
      <p>{title}</p>
      <span>{text}</span>
    </div>
  );
}

function StatusBadge({ status }) {
  const normalized = String(status || "idle");
  return <span className={`status-badge ${badgeClass(normalized)}`}>{normalized.replaceAll("_", " ")}</span>;
}

function AmbientField() {
  return (
    <div className="ambient-field" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

function buildPresentationState({ runId, status, artifacts, preview, validationBusy, qualityBusy, isStarting, error }) {
  const statuses = status?.agent_statuses || {};
  const activeAgent = STEPS.find((step) => statuses[step.id] === "running") || STEPS.find((step) => step.id === status?.current_agent);
  const failed = Boolean(error || (status?.errors || []).length);
  const validating = validationBusy;
  const complete = Boolean(status?.done && !failed);
  const phase =
    failed ? "failed" :
    validationBusy ? "validation" :
    qualityBusy ? "pitcher" :
    complete ? "complete" :
    isStarting || status?.current_agent === "queued" ? "submitted" :
    activeAgent?.id || (runId ? "processing" : "idle");

  const files = artifacts?.artifact_counts?.code_files ?? 0;
  const pitchFields = artifacts?.artifact_counts?.pitch_deck_fields ?? 0;
  const errors = status?.errors?.length ?? (error ? 1 : 0);
  const label = runId ? phaseLabel(phase, activeAgent) : "Ready";
  const metadata = {
    label,
    tone: failed ? "bad" : complete ? "good" : runId ? "active" : "idle",
    items: runId ? [`${files} files`, `${errors} errors`, `Pitch ${pitchFields}`] : [],
  };

  return {
    metadata,
    systemStatus: failed ? "System Alert" : runId && !complete ? "Processing" : "System Ready",
    tone: failed ? "bad" : runId && !complete ? "active" : "good",
    blackHole: getBlackHoleVisualState({ phase, activeAgent, validation: validating, preview }),
  };
}

function getBlackHoleVisualState({ phase, activeAgent }) {
  const map = {
    idle: { rotation: 46, disk: 0.34, halo: 0.34, starDistance: 190, starScale: 0.75, stream: 0, jet: 0, scan: 0, label: "Ready" },
    submitted: { rotation: 34, disk: 0.46, halo: 0.42, starDistance: 160, starScale: 0.9, stream: 0.16, jet: 0, scan: 0, label: "Idea captured" },
    analyst: { rotation: 29, disk: 0.56, halo: 0.52, starDistance: 138, starScale: 0.92, stream: 0.24, jet: 0, scan: 0, label: "Analyzing" },
    architect: { rotation: 23, disk: 0.68, halo: 0.66, starDistance: 115, starScale: 0.88, stream: 0.34, jet: 0, scan: 0, label: "Architecting" },
    builder: { rotation: 16, disk: 0.9, halo: 0.82, starDistance: 88, starScale: 0.78, stream: 0.66, jet: 0, scan: 0, label: "Building" },
    openhands: { rotation: 12, disk: 1, halo: 0.9, starDistance: 64, starScale: 0.66, stream: 0.92, jet: 0.18, scan: 0, label: "Refining" },
    pitcher: { rotation: 20, disk: 0.72, halo: 0.72, starDistance: 98, starScale: 0.82, stream: 0.28, jet: 0.1, scan: 0, label: "Pitching" },
    validation: { rotation: 24, disk: 0.7, halo: 0.74, starDistance: 104, starScale: 0.78, stream: 0.18, jet: 0, scan: 0.9, label: "Validating" },
    complete: { rotation: 32, disk: 0.58, halo: 0.78, starDistance: 118, starScale: 0.7, stream: 0, jet: 0.8, scan: 0.25, label: "Complete" },
    failed: { rotation: 18, disk: 0.82, halo: 0.52, starDistance: 92, starScale: 0.78, stream: 0.48, jet: 0, scan: 0, label: "Attention" },
    processing: { rotation: 22, disk: 0.7, halo: 0.62, starDistance: 112, starScale: 0.84, stream: 0.42, jet: 0, scan: 0, label: "Processing" },
  };
  const state = map[phase] || map.processing;
  return { ...state, phase, agentLabel: activeAgent?.label || (phase === "idle" ? "Waiting for an idea" : "SWARM orchestration") };
}

function getPreviewMainAction({ runId, hasFiles, preview }) {
  if (!runId || !hasFiles) return null;
  if (preview?.running) return { action: "launch", label: "Open App", icon: <ArrowUpRight className="h-4 w-4" /> };
  if (!preview?.prepared) return { action: "prepare", label: "Prepare", icon: <Download className="h-4 w-4" /> };
  if (!preview?.dependencies_installed) return { action: "install", label: "Install", icon: <TerminalSquare className="h-4 w-4" /> };
  return { action: "start", label: "Start", icon: <Play className="h-4 w-4" /> };
}

function previewActionDisabled(action, { runId, hasFiles, preview, busy }) {
  if (!runId || busy) return true;
  if (action === "stop") return !preview?.running;
  if (action === "start") return !hasFiles || !preview?.dependencies_installed;
  return !hasFiles;
}

function previewStatusLabel(preview, hasFiles) {
  if (!hasFiles) return "No app generated";
  if (preview?.running) return "Live";
  if (preview?.dependencies_installed) return "Installed";
  if (preview?.prepared) return "Prepared";
  return "Ready";
}

function actionLabel(action) {
  return {
    prepare: "Prepare",
    install: "Install",
    start: "Start",
    stop: "Stop",
    launch: "Launch",
  }[action] || action;
}

function phaseLabel(phase, activeAgent) {
  if (activeAgent) return activeAgent.label;
  return {
    idle: "Ready",
    submitted: "Queued",
    validation: "Validation",
    complete: "Complete",
    failed: "Needs attention",
    processing: "Processing",
    pitcher: "Pitch Strategist",
  }[phase] || "Processing";
}

function pipelineClass(status) {
  if (status === "done") return "is-done";
  if (status === "running") return "is-running";
  if (status === "waiting_for_trae") return "is-waiting-review";
  if (status === "error" || status === "failed") return "is-error";
  return "is-pending";
}

function badgeClass(status) {
  if (["done", "complete", "passed", "accepted", "target_met"].includes(status.toLowerCase())) return "good";
  if (["error", "failed"].includes(status.toLowerCase())) return "bad";
  if (["needs_revision", "waiting_for_trae"].includes(status.toLowerCase())) return "warn";
  if (["idle", "pending"].includes(status.toLowerCase())) return "idle";
  return "active";
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
  background: "#08101f",
  color: "#dbeafe",
  fontSize: "0.82rem",
};
