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
  const [runs, setRuns] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState("");
  const pollingRef = useRef(null);

  const agentStatuses = status?.agent_statuses || output?.summary?.agents || {};
  const generatedFileCount = output?.generated_files ? Object.keys(output.generated_files).length : 0;

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
        await refreshRuns();
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
    try {
      const [nextStatus, nextOutput] = await Promise.all([
        apiRequest(`/status/${nextRunId}`),
        apiRequest(`/output/${nextRunId}`),
      ]);
      setStatus(nextStatus);
      setOutput(nextOutput);
    } catch (loadError) {
      setError(loadError.message);
    }
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
            <button type="button" className="secondary-action" onClick={() => pollRun()} disabled={!runId}>
              Refresh status
            </button>
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

          <section className="tab-panel">{renderTab(activeTab, output, status)}</section>
        </section>
      </section>
    </main>
  );
}

function renderTab(activeTab, output, status) {
  if (!output && activeTab !== "Demo") {
    return <EmptyState title="No artifacts yet" detail="Generate an app to inspect this section." />;
  }

  if (activeTab === "Demo") {
    return (
      <div className="demo-grid">
        <InfoTile label="Current status" value={status?.status ? titleCase(status.status) : "Idle"} />
        <InfoTile label="Current agent" value={status?.current_agent ? titleCase(status.current_agent) : "None"} />
        <InfoTile label="Generated files" value={output?.generated_files ? Object.keys(output.generated_files).length : 0} />
        <InfoTile label="Pitch ready" value={output?.pitch_deck ? "Yes" : "No"} />
        <div className="wide-note">
          <h2>Demo</h2>
          <p>
            The generated app artifact is produced by the internal Builder agent. Preview launch,
            validation, and quality controls are added in the next frontend milestone.
          </p>
        </div>
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
    const files = output?.generated_files || {};
    return (
      <div className="code-view">
        <h2>Generated Files</h2>
        {Object.keys(files).length === 0 ? (
          <p className="muted">No generated code yet.</p>
        ) : (
          Object.entries(files).map(([path, content]) => (
            <details key={path}>
              <summary>{path}</summary>
              <pre>{content}</pre>
            </details>
          ))
        )}
      </div>
    );
  }

  return <JsonBlock title="Pitch Deck" value={output?.pitch_deck || {}} />;
}

function InfoTile({ label, value }) {
  return (
    <article className="info-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function JsonBlock({ title, value }) {
  return (
    <div className="json-block">
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

.status-pill {
  border-radius: 999px;
  border: 1px solid #bcccdc;
  background: white;
  color: #334e68;
  font-weight: 800;
  padding: 0.65rem 1rem;
}

.status-pill.complete {
  border-color: #86efac;
  color: #166534;
}

.status-pill.failed {
  border-color: #fecaca;
  color: #b42318;
}

.status-pill.running,
.status-pill.queued {
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
.empty-state {
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
.secondary-action,
.tabs button,
.run-list button {
  border: 0;
  border-radius: 8px;
}

.primary-action {
  background: #1565c0;
  color: white;
  font-weight: 800;
  padding: 0.9rem 1rem;
}

.primary-action:disabled {
  background: #9fb3c8;
  cursor: wait;
}

.secondary-action,
.run-list button {
  background: #edf2f7;
  color: #1f2933;
  padding: 0.7rem 0.8rem;
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

.demo-grid,
.overview {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
}

.info-tile,
.wide-note,
.empty-state {
  padding: 16px;
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
.code-view {
  grid-column: 1 / -1;
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
  max-height: 360px;
}

.muted,
.empty-state p,
.wide-note p {
  color: #697586;
}

@media (max-width: 980px) {
  .workspace,
  .timeline,
  .demo-grid,
  .overview {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
`;
