import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const AGENTS = ["analyst", "architect", "builder", "pitcher"];
const TABS = ["Demo", "Overview", "Requirements", "Architecture", "Code", "Pitch Deck"];

const defaultPrompt =
  "Build a salon appointment queue app with dashboard metrics, client follow ups, search, and local JSON data.";

export default function App() {
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [activeTab, setActiveTab] = useState("Demo");
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState(null);
  const [output, setOutput] = useState(null);
  const [artifacts, setArtifacts] = useState(null);
  const [preview, setPreview] = useState(null);
  const [validation, setValidation] = useState(null);
  const [quality, setQuality] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState("");
  const pollingRef = useRef(null);

  const agentStatuses = status?.agent_statuses || output?.summary?.agents || {};
  const generatedFiles = output?.generated_files || {};
  const generatedFileCount = Object.keys(generatedFiles).length;

  const selectedFilePath = selectedFile || Object.keys(generatedFiles)[0] || "";

  const statusLabel = useMemo(() => {
    if (!status) return "Idle";
    if (status.status === "complete") return "Complete";
    if (status.status === "failed") return "Failed";
    return status.current_agent ? `Running ${titleCase(status.current_agent)}` : titleCase(status.status);
  }, [status]);

  useEffect(() => {
    refreshRuns();
    return () => stopPolling();
  }, []);

  useEffect(() => {
    const filePaths = Object.keys(generatedFiles);
    if (!filePaths.length) {
      setSelectedFile("");
      return;
    }
    if (!selectedFile || !generatedFiles[selectedFile]) {
      setSelectedFile(filePaths[0]);
    }
  }, [generatedFiles, selectedFile]);

  async function refreshRuns() {
    try {
      const data = await apiRequest("/runs");
      setRuns(data.runs || []);
    } catch {
      setRuns([]);
    }
  }

  async function startRun() {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      setError("Enter a local business problem before generating an app.");
      return;
    }

    stopPolling();
    setIsGenerating(true);
    setError("");
    setOutput(null);
    setArtifacts(null);
    setPreview(null);
    setValidation(null);
    setQuality(null);
    setStatus(null);

    try {
      const started = await apiRequest("/run", {
        method: "POST",
        body: JSON.stringify({ prompt: trimmedPrompt }),
      });
      setRunId(started.run_id);
      await pollRun(started.run_id);
      pollingRef.current = window.setInterval(() => pollRun(started.run_id), 1600);
    } catch (runError) {
      setError(runError.message);
      setIsGenerating(false);
    }
  }

  async function pollRun(nextRunId = runId) {
    if (!nextRunId) return;

    try {
      const nextStatus = await apiRequest(`/status/${nextRunId}`);
      setStatus(nextStatus);
      if (nextStatus.status === "complete" || nextStatus.status === "failed") {
        stopPolling();
        setIsGenerating(false);
        const nextOutput = await apiRequest(`/output/${nextRunId}`);
        setOutput(nextOutput);
        await Promise.all([refreshRuns(), refreshArtifacts(nextRunId), refreshPreview(nextRunId)]);
      }
    } catch (pollError) {
      stopPolling();
      setIsGenerating(false);
      setError(pollError.message);
    }
  }

  async function loadRun(nextRunId) {
    stopPolling();
    setRunId(nextRunId);
    setError("");
    setPreview(null);
    setValidation(null);
    setQuality(null);
    try {
      const [nextStatus, nextOutput] = await Promise.all([
        apiRequest(`/status/${nextRunId}`),
        apiRequest(`/output/${nextRunId}`),
      ]);
      setStatus(nextStatus);
      setOutput(nextOutput);
      await Promise.all([refreshArtifacts(nextRunId), refreshPreview(nextRunId)]);
    } catch (loadError) {
      setError(loadError.message);
    }
  }

  async function refreshArtifacts(nextRunId = runId) {
    if (!nextRunId) return;
    try {
      const nextArtifacts = await apiRequest(`/artifacts/${nextRunId}`);
      setArtifacts(nextArtifacts);
      if (nextArtifacts.validation) setValidation(nextArtifacts.validation);
      if (nextArtifacts.quality) setQuality(nextArtifacts.quality);
    } catch {
      setArtifacts(null);
    }
  }

  async function refreshPreview(nextRunId = runId) {
    if (!nextRunId) return;
    try {
      setPreview(await apiRequest(`/preview/${nextRunId}/status`));
    } catch {
      setPreview(null);
    }
  }

  async function runPreviewAction(action) {
    if (!runId) return;
    setBusyAction(action);
    setError("");
    try {
      const nextPreview = await apiRequest(`/preview/${runId}/${action}`, { method: "POST" });
      setPreview(nextPreview);
      await refreshArtifacts(runId);
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusyAction("");
    }
  }

  async function runValidation() {
    if (!runId) return;
    setBusyAction("validate");
    setError("");
    try {
      const result = await apiRequest(`/validate/${runId}`, { method: "POST" });
      setValidation(result);
      await refreshArtifacts(runId);
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusyAction("");
    }
  }

  async function runQuality() {
    if (!runId) return;
    setBusyAction("quality");
    setError("");
    try {
      const result = await apiRequest(`/quality/${runId}`, { method: "POST" });
      setQuality(result);
      await refreshArtifacts(runId);
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusyAction("");
    }
  }

  function downloadGeneratedApp() {
    if (!runId) return;
    window.location.href = `${API_BASE}/download/${runId}`;
  }

  function stopPolling() {
    if (pollingRef.current) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }

  return (
    <main className="app-shell">
      <style>{styles}</style>

      <section className="topbar">
        <div>
          <p className="eyebrow">SWARM.AI</p>
          <h1>Local-Business App Factory</h1>
        </div>
        <div className={`status-pill ${status?.status || "idle"}`}>{statusLabel}</div>
      </section>

      <section className="workspace">
        <aside className="control-panel">
          <label className="prompt-field">
            <span>Business problem</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Describe the local business workflow to automate..."
            />
          </label>

          <button className="primary-action" type="button" disabled={isGenerating} onClick={startRun}>
            {isGenerating ? "Generating..." : "Generate app"}
          </button>

          <section className="run-card">
            <h2>Run Control</h2>
            <dl>
              <div>
                <dt>Run ID</dt>
                <dd>{runId || "No active run"}</dd>
              </div>
              <div>
                <dt>Generated files</dt>
                <dd>{generatedFileCount}</dd>
              </div>
              <div>
                <dt>Output directory</dt>
                <dd>{output?.output_dir || status?.output_dir || "Pending"}</dd>
              </div>
            </dl>
            <div className="button-row">
              <button type="button" className="secondary-action" onClick={() => pollRun()} disabled={!runId}>
                Refresh status
              </button>
              <button type="button" className="secondary-action" onClick={downloadGeneratedApp} disabled={!runId || !output}>
                Download app
              </button>
            </div>
          </section>

          <section className="run-card">
            <h2>Recent Runs</h2>
            {runs.length === 0 ? (
              <p className="muted">No runs yet.</p>
            ) : (
              <div className="run-list">
                {runs.slice(0, 6).map((run) => (
                  <button key={run.run_id} type="button" onClick={() => loadRun(run.run_id)}>
                    <span>{run.run_id.slice(0, 8)}</span>
                    <small>{titleCase(run.status)}</small>
                  </button>
                ))}
              </div>
            )}
          </section>
        </aside>

        <section className="main-panel">
          {error && <div className="error-banner">{error}</div>}

          <section className="timeline">
            {AGENTS.map((agent) => {
              const agentStatus = agentStatuses[agent]?.status || "pending";
              return (
                <article className={`agent ${agentStatus}`} key={agent}>
                  <span>{titleCase(agent)}</span>
                  <strong>{titleCase(agentStatus)}</strong>
                </article>
              );
            })}
          </section>

          <nav className="tabs" aria-label="Artifact tabs">
            {TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                className={activeTab === tab ? "active" : ""}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </nav>

          <section className="tab-panel">
            {renderTab({
              activeTab,
              artifacts,
              busyAction,
              output,
              preview,
              quality,
              runId,
              selectedFilePath,
              setSelectedFile,
              status,
              validation,
              onPreviewAction: runPreviewAction,
              onRefreshPreview: refreshPreview,
              onRunQuality: runQuality,
              onRunValidation: runValidation,
              onDownload: downloadGeneratedApp,
            })}
          </section>
        </section>
      </section>
    </main>
  );
}

function renderTab({
  activeTab,
  artifacts,
  busyAction,
  output,
  preview,
  quality,
  runId,
  selectedFilePath,
  setSelectedFile,
  status,
  validation,
  onPreviewAction,
  onRefreshPreview,
  onRunQuality,
  onRunValidation,
  onDownload,
}) {
  if (!output && activeTab !== "Demo") {
    return <EmptyState title="No artifacts yet" detail="Generate an app to inspect this section." />;
  }

  if (activeTab === "Demo") {
    return (
      <div className="demo-stack">
        <div className="demo-grid">
          <InfoTile label="Current status" value={status?.status ? titleCase(status.status) : "Idle"} />
          <InfoTile label="Preview" value={preview?.status ? titleCase(preview.status) : "Not prepared"} />
          <InfoTile label="Validation" value={validation?.status ? titleCase(validation.status) : "Not run"} />
          <InfoTile label="Quality" value={quality?.score ?? "Not scored"} />
        </div>

        <PreviewPanel
          busyAction={busyAction}
          preview={preview}
          runId={runId}
          onAction={onPreviewAction}
          onRefresh={onRefreshPreview}
        />

        <ValidationPanel
          busyAction={busyAction}
          validation={validation}
          quality={quality}
          onRunQuality={onRunQuality}
          onRunValidation={onRunValidation}
        />
      </div>
    );
  }

  if (activeTab === "Overview") {
    return (
      <div className="overview">
        <InfoTile label="Run status" value={output?.status ? titleCase(output.status) : "Unknown"} />
        <InfoTile label="Requirements" value={output?.requirements ? "Ready" : "Missing"} />
        <InfoTile label="Architecture" value={output?.architecture ? "Ready" : "Missing"} />
        <InfoTile label="Pitch deck" value={output?.pitch_deck ? "Ready" : "Missing"} />
        <InfoTile label="Artifacts" value={artifacts?.generated_file_count ?? Object.keys(output?.generated_files || {}).length} />
        <InfoTile label="Quality target" value={quality?.passed ? "Passed" : "Pending"} />
        <div className="wide-note">
          <h2>Artifact Controls</h2>
          <div className="button-row">
            <button type="button" className="secondary-action" onClick={onDownload} disabled={!runId}>
              Download generated app
            </button>
            <button type="button" className="secondary-action" onClick={onRunValidation} disabled={!runId || busyAction === "validate"}>
              {busyAction === "validate" ? "Validating..." : "Run validation"}
            </button>
            <button type="button" className="secondary-action" onClick={onRunQuality} disabled={!runId || busyAction === "quality"}>
              {busyAction === "quality" ? "Scoring..." : "Score quality"}
            </button>
          </div>
        </div>
        <JsonBlock title="Run summary" value={output?.summary || {}} />
      </div>
    );
  }

  if (activeTab === "Requirements") {
    return <JsonBlock title="Requirements" value={output?.requirements || {}} />;
  }

  if (activeTab === "Architecture") {
    return <JsonBlock title="Architecture" value={output?.architecture || {}} />;
  }

  if (activeTab === "Code") {
    return (
      <CodeExplorer
        files={output?.generated_files || {}}
        selectedFilePath={selectedFilePath}
        setSelectedFile={setSelectedFile}
      />
    );
  }

  return <JsonBlock title="Pitch Deck" value={output?.pitch_deck || {}} />;
}

function PreviewPanel({ busyAction, preview, runId, onAction, onRefresh }) {
  const isRunning = preview?.status === "running";
  return (
    <section className="panel-section">
      <div className="section-heading">
        <div>
          <h2>Generated App Preview</h2>
          <p>Launches the generated Express API on 3001 and Vite frontend on 6200.</p>
        </div>
        <span className={`mini-pill ${preview?.status || "stopped"}`}>{preview?.status ? titleCase(preview.status) : "Not prepared"}</span>
      </div>

      <div className="button-row">
        {["prepare", "install", "start", "stop", "launch"].map((action) => (
          <button
            key={action}
            type="button"
            className={action === "launch" ? "primary-small" : "secondary-action"}
            disabled={!runId || Boolean(busyAction)}
            onClick={() => onAction(action)}
          >
            {busyAction === action ? `${titleCase(action)}...` : titleCase(action)}
          </button>
        ))}
        <button type="button" className="secondary-action" disabled={!runId} onClick={() => onRefresh()}>
          Refresh preview
        </button>
      </div>

      <div className="link-grid">
        <LinkTile label="Generated frontend" href={preview?.frontend_url} enabled={isRunning} />
        <LinkTile label="API health" href={preview?.api_health_url} enabled={isRunning} />
        <LinkTile label="API metrics" href={preview?.api_metrics_url} enabled={isRunning} />
      </div>

      <JsonBlock title="Preview status" value={preview || { status: "not prepared" }} compact />
    </section>
  );
}

function ValidationPanel({ busyAction, validation, quality, onRunQuality, onRunValidation }) {
  return (
    <section className="panel-grid">
      <div className="panel-section">
        <div className="section-heading">
          <div>
            <h2>Validation</h2>
            <p>Runs install, check, test, and build inside the generated app.</p>
          </div>
          <span className={`mini-pill ${validation?.status || "pending"}`}>{validation?.status ? titleCase(validation.status) : "Not run"}</span>
        </div>
        <button type="button" className="primary-small" disabled={Boolean(busyAction)} onClick={onRunValidation}>
          {busyAction === "validate" ? "Validating..." : "Run validation"}
        </button>
        <CommandList validation={validation} />
      </div>

      <div className="panel-section">
        <div className="section-heading">
          <div>
            <h2>Quality</h2>
            <p>Scores completeness, workflows, coverage, localization, runnable quality, and polish.</p>
          </div>
          <span className={`mini-pill ${quality?.passed ? "passed" : "pending"}`}>{quality?.score ?? "Not scored"}</span>
        </div>
        <button type="button" className="primary-small" disabled={Boolean(busyAction)} onClick={onRunQuality}>
          {busyAction === "quality" ? "Scoring..." : "Score quality"}
        </button>
        {quality ? (
          <div className="score-list">
            {Object.entries(quality.scores || {}).map(([name, score]) => (
              <div key={name}>
                <span>{titleCase(name)}</span>
                <strong>{score}</strong>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No quality score yet.</p>
        )}
      </div>
    </section>
  );
}

function CommandList({ validation }) {
  if (!validation?.commands?.length) {
    return <p className="muted">No validation commands have run yet.</p>;
  }
  return (
    <div className="command-list">
      {validation.commands.map((command, index) => (
        <details key={`${command.command?.join(" ")}-${index}`}>
          <summary>
            <span>{command.command?.join(" ")}</span>
            <strong>{command.returncode === 0 ? "passed" : `exit ${command.returncode}`}</strong>
          </summary>
          <pre>{[command.stdout, command.stderr, command.error].filter(Boolean).join("\n\n") || "No output"}</pre>
        </details>
      ))}
    </div>
  );
}

function LinkTile({ label, href, enabled }) {
  return (
    <a className={`link-tile ${enabled ? "" : "disabled"}`} href={enabled ? href : undefined} target="_blank" rel="noreferrer">
      <span>{label}</span>
      <strong>{enabled ? href : "Start preview first"}</strong>
    </a>
  );
}

function CodeExplorer({ files, selectedFilePath, setSelectedFile }) {
  const filePaths = Object.keys(files);
  const content = selectedFilePath ? files[selectedFilePath] || "" : "";
  if (!filePaths.length) {
    return (
      <div className="code-view">
        <h2>Generated Files</h2>
        <p className="muted">No generated code yet.</p>
      </div>
    );
  }

  return (
    <div className="code-explorer">
      <aside className="file-list">
        <h2>Generated Files</h2>
        {filePaths.map((path) => (
          <button
            key={path}
            type="button"
            className={path === selectedFilePath ? "active" : ""}
            onClick={() => setSelectedFile(path)}
          >
            {path}
          </button>
        ))}
      </aside>
      <section className="code-pane">
        <div className="code-toolbar">
          <h2>{selectedFilePath}</h2>
          <span>{content.split("\n").length} lines</span>
        </div>
        <pre className="highlighted-code">
          <code>{highlightCode(content, selectedFilePath)}</code>
        </pre>
      </section>
    </div>
  );
}

function highlightCode(content, path) {
  if (!content) return null;
  const language = languageForPath(path);
  return content.split(/(\b(?:const|let|var|function|return|import|from|export|async|await|if|else|try|catch|class|new)\b|\"[^\"\n]*\"|'[^'\n]*'|`[^`]*`|\/\/[^\n]*|#[^\n]*)/g).map((part, index) => {
    let className = "";
    if (/^(const|let|var|function|return|import|from|export|async|await|if|else|try|catch|class|new)$/.test(part)) {
      className = "tok-keyword";
    } else if (/^(\"[^\"\n]*\"|'[^'\n]*'|`[^`]*`)$/.test(part)) {
      className = "tok-string";
    } else if (/^(\/\/|#)/.test(part)) {
      className = "tok-comment";
    } else if (language === "json" && /^(true|false|null)$/.test(part)) {
      className = "tok-keyword";
    }
    return (
      <span className={className} key={`${index}-${part.slice(0, 8)}`}>
        {part}
      </span>
    );
  });
}

function languageForPath(path) {
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".md")) return "markdown";
  return "javascript";
}

function InfoTile({ label, value }) {
  return (
    <article className="info-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function JsonBlock({ title, value, compact = false }) {
  return (
    <div className={`json-block ${compact ? "compact" : ""}`}>
      <h2>{title}</h2>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

function EmptyState({ title, detail }) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{detail}</p>
    </div>
  );
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

function titleCase(value) {
  return String(value || "")
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const styles = `
:root {
  color: #1f2933;
  background: #f5f7fa;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

button,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.app-shell {
  margin: 0 auto;
  max-width: 1380px;
  padding: 24px;
}

.topbar {
  align-items: center;
  display: flex;
  gap: 18px;
  justify-content: space-between;
  margin-bottom: 20px;
}

.eyebrow {
  color: #1f6f8b;
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  margin: 0 0 4px;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  font-size: 2rem;
  margin-bottom: 0;
}

.status-pill,
.mini-pill {
  border-radius: 999px;
  border: 1px solid #bcccdc;
  background: white;
  color: #334e68;
  font-weight: 800;
  padding: 0.65rem 1rem;
}

.mini-pill {
  font-size: 0.82rem;
  padding: 0.45rem 0.7rem;
  white-space: nowrap;
}

.status-pill.complete,
.mini-pill.running,
.mini-pill.installed,
.mini-pill.prepared,
.mini-pill.passed {
  border-color: #86efac;
  color: #166534;
}

.status-pill.failed,
.mini-pill.failed,
.mini-pill.install_failed {
  border-color: #fecaca;
  color: #b42318;
}

.status-pill.running,
.status-pill.queued,
.mini-pill.pending {
  border-color: #bae6fd;
  color: #075985;
}

.workspace {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(300px, 390px) 1fr;
}

.control-panel,
.main-panel,
.run-card,
.info-tile,
.wide-note,
.empty-state,
.panel-section {
  background: white;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
}

.control-panel {
  align-self: start;
  display: grid;
  gap: 16px;
  padding: 18px;
}

.prompt-field {
  display: grid;
  gap: 8px;
  font-weight: 800;
}

textarea {
  border: 1px solid #bcccdc;
  border-radius: 8px;
  min-height: 170px;
  padding: 0.8rem;
  resize: vertical;
  width: 100%;
}

.primary-action,
.primary-small,
.secondary-action,
.tabs button,
.run-list button,
.file-list button {
  border: 0;
  border-radius: 8px;
}

.primary-action,
.primary-small {
  background: #1565c0;
  color: white;
  font-weight: 800;
}

.primary-action {
  padding: 0.9rem 1rem;
}

.primary-small {
  padding: 0.7rem 0.85rem;
}

.primary-action:disabled {
  background: #9fb3c8;
}

.secondary-action,
.run-list button,
.file-list button {
  background: #edf2f7;
  color: #1f2933;
  padding: 0.7rem 0.8rem;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.run-card {
  padding: 16px;
}

.run-card h2 {
  font-size: 1rem;
  margin-bottom: 12px;
}

dl {
  display: grid;
  gap: 10px;
  margin: 0 0 14px;
}

dt {
  color: #52606d;
  font-size: 0.75rem;
  font-weight: 800;
  text-transform: uppercase;
}

dd {
  margin: 2px 0 0;
  overflow-wrap: anywhere;
}

.run-list {
  display: grid;
  gap: 8px;
}

.run-list button {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.main-panel {
  min-width: 0;
  padding: 18px;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #b42318;
  margin-bottom: 14px;
  padding: 0.8rem;
}

.timeline {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(130px, 1fr));
  margin-bottom: 16px;
}

.agent {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  padding: 12px;
}

.agent span {
  color: #52606d;
  display: block;
  font-size: 0.8rem;
}

.agent strong {
  display: block;
  margin-top: 4px;
}

.agent.complete {
  border-color: #86efac;
  background: #f0fdf4;
}

.agent.running {
  border-color: #bae6fd;
  background: #f0f9ff;
}

.agent.failed {
  border-color: #fecaca;
  background: #fef2f2;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.tabs button {
  background: #edf2f7;
  color: #334e68;
  padding: 0.65rem 0.85rem;
}

.tabs button.active {
  background: #1565c0;
  color: white;
}

.tab-panel {
  min-height: 460px;
}

.demo-stack {
  display: grid;
  gap: 16px;
}

.demo-grid,
.overview,
.panel-grid,
.link-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
}

.panel-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.link-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 14px 0;
}

.info-tile,
.wide-note,
.empty-state,
.panel-section {
  padding: 16px;
}

.section-heading {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-heading h2,
.section-heading p {
  margin-bottom: 4px;
}

.info-tile span {
  color: #52606d;
  display: block;
  font-size: 0.82rem;
}

.info-tile strong {
  display: block;
  font-size: 1.45rem;
  margin-top: 6px;
  overflow-wrap: anywhere;
}

.wide-note,
.json-block,
.code-view,
.panel-section {
  grid-column: 1 / -1;
}

.panel-grid .panel-section {
  grid-column: auto;
}

.json-block h2,
.code-view h2 {
  margin-bottom: 10px;
}

pre {
  background: #102a43;
  border-radius: 8px;
  color: #d9e2ec;
  max-height: 560px;
  overflow: auto;
  padding: 16px;
  white-space: pre-wrap;
}

.json-block.compact pre {
  max-height: 220px;
}

details {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  margin-bottom: 10px;
}

summary {
  cursor: pointer;
  font-weight: 800;
  padding: 12px 14px;
}

details pre {
  border-radius: 0 0 8px 8px;
  margin: 0;
  max-height: 260px;
}

.command-list summary {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.score-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.score-list div {
  align-items: center;
  background: #f8fafc;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  padding: 10px;
}

.link-tile {
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  color: #075985;
  display: grid;
  gap: 5px;
  padding: 12px;
  text-decoration: none;
}

.link-tile.disabled {
  color: #697586;
  pointer-events: none;
}

.link-tile span {
  color: #52606d;
  font-size: 0.82rem;
}

.link-tile strong {
  overflow-wrap: anywhere;
}

.code-explorer {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(230px, 320px) 1fr;
}

.file-list {
  background: white;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  display: grid;
  gap: 8px;
  max-height: 690px;
  overflow: auto;
  padding: 14px;
}

.file-list h2 {
  font-size: 1rem;
  margin-bottom: 6px;
}

.file-list button {
  overflow-wrap: anywhere;
  text-align: left;
}

.file-list button.active {
  background: #1565c0;
  color: white;
}

.code-pane {
  min-width: 0;
}

.code-toolbar {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 10px;
}

.code-toolbar h2 {
  font-size: 1rem;
  margin: 0;
  overflow-wrap: anywhere;
}

.highlighted-code {
  margin: 0;
}

.tok-keyword {
  color: #7dd3fc;
}

.tok-string {
  color: #86efac;
}

.tok-comment {
  color: #94a3b8;
}

.muted,
.empty-state p,
.wide-note p,
.section-heading p {
  color: #697586;
}

@media (max-width: 980px) {
  .workspace,
  .timeline,
  .demo-grid,
  .overview,
  .panel-grid,
  .link-grid,
  .code-explorer {
    grid-template-columns: 1fr;
  }

  .topbar,
  .section-heading,
  .code-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
`;
