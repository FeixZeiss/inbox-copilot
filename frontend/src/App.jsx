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

export default function App() {
  const [status, setStatus] = useState(STATUS.idle);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [statusInfo, setStatusInfo] = useState(null);
  const [secretsStatus, setSecretsStatus] = useState(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [tokenUploadMessage, setTokenUploadMessage] = useState("");
  const [oauthMessage, setOauthMessage] = useState("");
  const [oauthUrl, setOauthUrl] = useState("");

  async function fetchSecretsStatus() {
    try {
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
    if (!summary && !statusInfo?.metrics) {
      return null;
    }
    const current = statusInfo?.metrics || {};
    return [
      { label: "Processed", value: summary?.processed ?? current.processed },
      { label: "Seen", value: summary?.message_ids_seen ?? current.message_ids_seen },
      { label: "Skipped", value: summary?.skipped_deleted ?? current.skipped_deleted },
      { label: "Errors", value: summary?.errors ?? current.errors },
    ];
  }, [summary, statusInfo]);

  useEffect(() => {
    fetchStatus();
    fetchSecretsStatus();
  }, []);

  useEffect(() => {
    if (status !== STATUS.running) {
      return;
    }
    const timer = setInterval(fetchStatus, 1000);
    return () => clearInterval(timer);
  }, [status]);

  async function handleRun() {
    setStatus(STATUS.running);
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
      setSummary(payload.summary || null);
      setStatus(STATUS.done);
      fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setStatus(STATUS.error);
    }
  }

  async function handleUploadCredentials(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setUploadMessage("");
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
      setUploadMessage("credentials.json gespeichert.");
      fetchSecretsStatus();
    } catch (err) {
      setUploadMessage(err instanceof Error ? err.message : "Upload fehlgeschlagen.");
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
      setTokenUploadMessage("gmail_token.json gespeichert.");
      fetchSecretsStatus();
    } catch (err) {
      setTokenUploadMessage(
        err instanceof Error ? err.message : "Upload fehlgeschlagen."
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
        throw new Error(payload?.detail || "OAuth fehlgeschlagen");
      }
      const payload = await res.json();
      const url = payload?.auth_url;
      if (!url) {
        throw new Error("OAuth-URL fehlt");
      }
      const popup = window.open(url, "_blank", "noopener,noreferrer");
      if (!popup) {
        setOauthUrl(url);
        setOauthMessage("Popup blockiert. Bitte Link manuell öffnen.");
      } else {
        setOauthMessage("Bitte im neuen Fenster anmelden.");
      }
    } catch (err) {
      setOauthMessage(err instanceof Error ? err.message : "OAuth fehlgeschlagen.");
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
            {status === STATUS.running ? "Running..." : "Run Once"}
          </button>
          <div className="status">
            Status: <strong>{status}</strong>
            {statusInfo?.detail ? ` — ${statusInfo.detail}` : ""}
          </div>
        </div>
      </header>

      <section className="panel">
        <div className="panel-header">
          <h2>Last Run Summary</h2>
          <span className="timestamp">
            {summary?.latest_internal_date_ms
              ? new Date(summary.latest_internal_date_ms).toLocaleString()
              : "No run yet"}
          </span>
        </div>
        {metrics ? (
          <div className="metrics">
            {metrics.map((item) => (
              <div key={item.label} className="metric">
                <span>{item.label}</span>
                <strong>{formatCount(item.value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="placeholder">Trigger a run to see metrics.</div>
        )}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Gmail Setup</h2>
          <span className="timestamp">
            {secretsStatus?.secrets_dir ? secretsStatus.secrets_dir : ""}
          </span>
        </div>
        <div className="setup-grid">
          <div>
            <strong>1) Credentials hochladen</strong>
            <p className="muted">
              Die Datei wird nur lokal im Ordner secrets/ gespeichert.
            </p>
            <input
              type="file"
              accept="application/json"
              onChange={handleUploadCredentials}
            />
            {uploadMessage && <div className="hint">{uploadMessage}</div>}
          </div>
          <div>
            <strong>2) Token hochladen (optional)</strong>
            <p className="muted">
              Nutze das, wenn du schon einen gmail_token.json hast.
            </p>
            <input
              type="file"
              accept="application/json"
              onChange={handleUploadToken}
            />
            {tokenUploadMessage && <div className="hint">{tokenUploadMessage}</div>}
          </div>
          <div>
            <strong>3) OAuth starten</strong>
            <p className="muted">
              Öffnet ein Browser-Fenster für Google Login und speichert den Token lokal.
            </p>
            <button className="secondary" onClick={handleOAuth}>
              Gmail verbinden
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
          Credentials:{" "}
          <strong>{secretsStatus?.credentials_present ? "vorhanden" : "fehlt"}</strong>
          {" · "}Token:{" "}
          <strong>{secretsStatus?.token_present ? "vorhanden" : "fehlt"}</strong>
        </div>
      </section>

      <section className="panel grid">
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
    </div>
  );
}
