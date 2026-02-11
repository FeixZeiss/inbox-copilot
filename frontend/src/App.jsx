import React, { useEffect, useMemo, useState } from "react";

const STATUS = {
  idle: "idle",
  running: "running",
  done: "done",
  error: "error",
};

function formatCount(value) {
  return typeof value === "number" ? value.toString() : "-";
}

function getRecentActionView(action) {
  if (action?.type === "draft_summary") {
    return null;
  }

  if (action?.type === "draft") {
    const recipient = action.to || "-";
    const subject = action.subject || "-";
    return {
      kind: "label",
      title: "Draft created",
      primary: `An: ${recipient}`,
      secondary: `Betreff: ${subject}`,
      badges: [],
    };
  }

  return {
    kind: "label",
    title: "Label applied",
    primary: action.subject || action.from || action.message_id || "Email action",
    secondary: action.from ? `From: ${action.from}` : action.message_id ? `Message: ${action.message_id}` : null,
    badges: [action.label ? `Label: ${action.label}` : null].filter(Boolean),
  };
}

export default function App() {
  // UI state: run lifecycle and current backend snapshots.
  const [status, setStatus] = useState(STATUS.idle);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [statusInfo, setStatusInfo] = useState(null);
  const [secretsStatus, setSecretsStatus] = useState(null);
  // UI state: upload/OAuth feedback messages.
  const [uploadMessage, setUploadMessage] = useState("");
  const [tokenUploadMessage, setTokenUploadMessage] = useState("");
  const [openaiTokenUploadMessage, setOpenAITokenUploadMessage] = useState("");
  const [oauthMessage, setOauthMessage] = useState("");
  const [oauthUrl, setOauthUrl] = useState("");
  const [draftDryRun, setDraftDryRun] = useState(true);
  const [draftSummary, setDraftSummary] = useState(null);
  const [lastSummaryAt, setLastSummaryAt] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [logs, setLogs] = useState([])

  async function fetchSecretsStatus() {
    try {
      // Keep the UI in sync with backend secret availability.
      const res = await fetch("/api/secrets/status");
      if (!res.ok) {
        return;
      }
      const payload = await res.json();
      if (payload?.ok) {
        setSecretsStatus(payload);
      }
    } catch {
      // Ignore status polling errors.
    }
  }

  async function fetchStatus() {
    try {
      // Poll run status while a job is in flight.
      const res = await fetch("/api/run/status");
      if (!res.ok) {
        return;
      }
      const payload = await res.json();
      if (payload?.ok) {
        setStatusInfo(payload.status || null);
      }
    } catch {
      // Ignore status polling errors.
    }
  }

  const metrics = useMemo(() => {
    // Merge live metrics with the last summary for a stable display.
    if (!summary && !statusInfo?.metrics && !draftSummary) {
      return null;
    }
    const current = statusInfo?.metrics || {};
    const processedLabels = summary?.processed ?? current.processed;
    const processedDrafts = draftSummary
      ? (draftSummary.created ?? 0) + (draftSummary.dry_run ?? 0)
      : 0;
    const errorsTotal = (summary?.errors ?? current.errors ?? 0)
      + (draftSummary?.errors ?? 0);
    return [
      { label: "Processed Labels", value: processedLabels },
      { label: "Processed Drafts", value: processedDrafts },
      { label: "Seen", value: summary?.message_ids_seen ?? current.message_ids_seen },
      { label: "Errors", value: errorsTotal },
    ];
  }, [summary, statusInfo, draftSummary]);

  useEffect(() => {
    // Initial load: fetch baseline status and secrets once.
    fetchStatus();
    fetchSecretsStatus();
  }, []);

  useEffect(() => {
    if (status !== STATUS.running) {
      return;
    }
    // Poll only while the backend is running to reduce load.
    const timer = setInterval(fetchStatus, 1000);
    return () => clearInterval(timer);
  }, [status]);

  useEffect(() => {
    const originalLog = console.log;

    console.log = (...args) => {
      setLogs((prev) => [...prev, args.join(" ")]);
      originalLog(...args);
    };

    return () => {
      console.log = originalLog;
    };
  }, []);

  async function handleRun() {
    // Optimistically mark as running; backend will confirm via status API.
    setStatus(STATUS.running);
    setActiveJob("run");
    setSummary(null);
    setError("");
    fetchStatus();

    try {
      const res = await fetch("/api/run", { method: "POST" });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const payload = await res.json();
      if (!payload?.ok) {
        throw new Error("Backend returned ok=false");
      }
      // Store the final summary so the UI can show totals.
      setSummary(payload.summary || null);
      setLastSummaryAt(Date.now());
      setStatus(STATUS.done);
      setActiveJob(null);
      fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus(STATUS.error);
      setActiveJob(null);
    }
  }

  async function handleCreateDrafts() {
    setStatus(STATUS.running);
    setActiveJob("drafts");
    setError("");
    fetchStatus();

    try {
      const res = await fetch("/api/drafts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: draftDryRun }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = payload?.detail;
        if (detail?.code === "openai_token_invalid") {
          const msg = detail?.message || "The uploaded OpenAI token is invalid.";
          const shouldDelete = window.confirm(
            `${msg}\n\nDo you want to delete the uploaded OpenAI token now?`
          );
          if (shouldDelete) {
            const deleteRes = await fetch("/api/secrets/openai_token/delete", {
              method: "POST",
            });
            const deletePayload = await deleteRes.json().catch(() => ({}));
            if (!deleteRes.ok || !deletePayload?.ok) {
              throw new Error("Token is invalid. Failed to delete the token file.");
            }
            fetchSecretsStatus();
            throw new Error("OpenAI token is invalid and was deleted. Please upload a valid token.");
          }
          throw new Error("OpenAI token is invalid. Token was kept.");
        }
        throw new Error(
          typeof detail === "string" ? detail : detail?.message || `Request failed (${res.status})`
        );
      }
      if (!payload?.ok) {
        throw new Error("Backend returned ok=false");
      }

      setDraftSummary(payload.summary || null);
      setLastSummaryAt(Date.now());
      setStatus(STATUS.done);
      setActiveJob(null);
      fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus(STATUS.error);
      setActiveJob(null);
    }
  }

  async function handleUploadCredentials(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setUploadMessage("");
    // Multipart upload for credentials.json.
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/secrets/credentials", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "Upload failed");
      }
      setUploadMessage("credentials.json saved.");
      fetchSecretsStatus();
    } catch (err) {
      setUploadMessage(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      event.target.value = "";
    }
  }

  async function handleUploadToken(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setTokenUploadMessage("");
    // Multipart upload for gmail_token.json.
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/secrets/token", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "Upload failed");
      }
      setTokenUploadMessage("gmail_token.json saved.");
      fetchSecretsStatus();
    } catch (err) {
      setTokenUploadMessage(
        err instanceof Error ? err.message : "Upload failed."
      );
    } finally {
      event.target.value = "";
    }
  }

  async function handleUploadOpenAIToken(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setOpenAITokenUploadMessage("");
    // Multipart upload for openai_token.json.
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/secrets/openai_token", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "Upload failed");
      }
      setOpenAITokenUploadMessage("openai_token.json saved.");
      fetchSecretsStatus();
    } catch (err) {
      setOpenAITokenUploadMessage(
        err instanceof Error ? err.message : "Upload failed."
      );
    } finally {
      event.target.value = "";
    }
  } 

  async function handleOAuth() {
    setOauthMessage("");
    setOauthUrl("");
    try {
      const res = await fetch("/api/secrets/oauth", { method: "POST" });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "OAuth failed");
      }
      const payload = await res.json();
      const url = payload?.auth_url;
      if (!url) {
        throw new Error("Missing OAuth URL");
      }
      // Try opening a popup; if blocked, show the URL so the user can continue.
      const popup = window.open(url, "_blank", "noopener,noreferrer");
      if (!popup) {
        setOauthUrl(url);
        setOauthMessage("Popup blocked. Please open the link manually.");
      } else {
        setOauthMessage("Please sign in in the new window.");
      }
    } catch (err) {
      setOauthMessage(err instanceof Error ? err.message : "OAuth failed.");
    }
  }

  return (
    <div className="page">
      <div className="glow" />
      <header className="hero">
        <span className="chip">Inbox Copilot</span>
        <h1>Automate your inbox with calm, reliable rules.</h1>
        <p>
          Run a single scan, label what matters, and keep the signal clean. The
          backend will analyze your latest Gmail messages and update labels.
        </p>
        <div className="actions">
          <button
            className="primary"
            onClick={handleRun}
            disabled={status === STATUS.running}
          >
            {status === STATUS.running && activeJob === "run" ? "Adding Labels..." : "Add Labels"}
          </button>
          <button
            className="secondary"
            onClick={handleCreateDrafts}
            disabled={status === STATUS.running}
          >
            {status === STATUS.running && activeJob === "drafts" ? "Creating Drafts..." : "Create Drafts"}
          </button>
          <label className="checkbox-inline">
            <input
              type="checkbox"
              checked={draftDryRun}
              onChange={(event) => setDraftDryRun(event.target.checked)}
              disabled={status === STATUS.running}
            />
            Dry run (no draft creation)
          </label>
          <div className="status">
            Status: <strong>{status}</strong>
            {statusInfo?.detail ? ` — ${statusInfo.detail}` : ""}
          </div>
        </div>
      </header>

      <section className="panel">
        {/* Run summary panel with metrics and error feedback. */}
        <div className="panel-header">
          <h2>Last Run Summary</h2>
          <span className="timestamp">
            {lastSummaryAt
              ? new Date(lastSummaryAt).toLocaleString()
              : "No run yet"}
          </span>
        </div>
        {metrics ? (
          // Render metrics when we have either live or summary data.
          <div className="metrics">
            {metrics.map((item) => (
              <div key={item.label} className="metric">
                <span>{item.label}</span>
                <strong>{formatCount(item.value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          // Empty-state copy for first-time users.
          <div className="placeholder">Trigger a run to see metrics.</div>
        )}
        {error && <div className="error">{error}</div>}
        {statusInfo?.recent_errors?.length ? (
          <div className="error-list">
            {statusInfo.recent_errors.slice(0, 10).map((item, index) => (
              <div key={`${item.message_id}-${index}`} className="error-item">
                Error: {item.error} · Email: {item.from || item.subject || item.message_id}
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        {/* Gmail setup panel: credentials, token upload, or OAuth flow. */}
        <div className="panel-header">
          <h2>Gmail Setup</h2>
          <span className="timestamp">
            {secretsStatus?.secrets_dir ? secretsStatus.secrets_dir : ""}
          </span>
        </div>
        <div className="setup-grid">
          <div>
            <strong>1) Upload credentials</strong>
            <p className="muted">
              The file is stored locally in the secrets/ folder only.
            </p>
            {/* Upload Google OAuth client credentials (credentials.json). */}
            <input
              type="file"
              accept="application/json"
              onChange={handleUploadCredentials}
            />
            {uploadMessage && <div className="hint">{uploadMessage}</div>}
          </div>
          <div>
            <strong>2) Upload Gmail token (optional)</strong>
            <p className="muted">
              Use this if you already have a gmail_token.json file.
            </p>
            {/* Upload an existing Gmail token if already authenticated. */}
            <input
              type="file"
              accept="application/json"
              onChange={handleUploadToken}
            />
            {tokenUploadMessage && <div className="hint">{tokenUploadMessage}</div>}
          </div>
          <div>
            <strong>3) Upload OpenAI token (optional)</strong>
            <p className="muted">
              Use this if you already have an OpenAI token and want intelligent email drafting.
            </p>
            {/* Upload an existing OpenAI token if already authenticated. */}
            <input
              type="file"
              accept="application/json"
              onChange={handleUploadOpenAIToken}
            />
            {openaiTokenUploadMessage && <div className="hint">{openaiTokenUploadMessage}</div>}
          </div>
          <div>
            <strong>4) Start OAuth</strong>
            <p className="muted">
              Opens a browser window for Google sign-in and stores the token locally.
            </p>
            {/* Start OAuth if the token is not available yet. */}
            <button className="secondary" onClick={handleOAuth}>
              Connect Gmail
            </button>
            {oauthMessage && <div className="hint">{oauthMessage}</div>}
            {oauthUrl && (
              <div className="hint">
                OAuth-Link: <a href={oauthUrl}>{oauthUrl}</a>
              </div>
            )}
          </div>
        </div>
        <div className="status-line">
          {/* Quick status line for current secret availability. */}
          Credentials:{" "}
          <strong>{secretsStatus?.credentials_present ? "present" : "missing"}</strong>
          {" · "}Token:{" "}
          <strong>{secretsStatus?.token_present ? "present" : "missing"}</strong>
          {" · "}OpenAI Token:{" "}
          <strong>{secretsStatus?.openai_token_present ? "present" : "missing"}</strong>
        </div>
      </section>

      <section className="panel grid">
        {/* High-level explanation panel for non-technical users. */}
        <div>
          <h3>What happens</h3>
          <ul>
            <li>Fetch recent messages from Gmail</li>
            <li>Classify with rules and heuristics</li>
            <li>Apply labels and archive when needed</li>
          </ul>
        </div>
        <div>
          <h3>Safety</h3>
          <ul>
            <li>OAuth tokens remain local</li>
            <li>Actions are logged</li>
            <li>State avoids double-processing</li>
          </ul>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Latest Actions</h2>
        </div>
        {(statusInfo?.recent_actions || []).some((a) => getRecentActionView(a)) ? (
          <div className="action-list">
            {statusInfo.recent_actions.map((a, i) => {
              const view = getRecentActionView(a);
              if (!view) {
                return null;
              }
              return (
                <div key={`${view.kind}-${i}`} className={`action-card action-${view.kind}`}>
                  <div className="action-head">
                    <strong>{view.title}</strong>
                    {view.badges?.length ? (
                      <div className="action-badges">
                        {view.badges.map((badge) => (
                          <span key={badge} className="action-badge">{badge}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="action-primary">{view.primary}</div>
                  {view.secondary ? <div className="action-secondary">{view.secondary}</div> : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="placeholder">No actions yet.</div>
        )}
      </section>

    </div>
  );
}
