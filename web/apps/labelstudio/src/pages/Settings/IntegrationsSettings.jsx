import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@humansignal/ui";
import { Spinner } from "../../components";
import { modal } from "../../components/Modal/Modal";
import { useAPI } from "../../providers/ApiProvider";
import { useProject } from "../../providers/ProjectProvider";
import { cn } from "../../utils/bem";
import "./IntegrationsSettings.prefix.css";

const rootClass = cn("integrations");

const LangfuseConfigModal = ({ existing, project, onSave, onClose }) => {
  const api = useAPI();
  const [host, setHost] = useState(existing?.langfuse_host || "https://cloud.langfuse.com");
  const [publicKey, setPublicKey] = useState(existing?.langfuse_public_key || "");
  const [secretKey, setSecretKey] = useState("");
  const [nameFilter, setNameFilter] = useState(existing?.trace_name_filter || "");
  const [tagFilter, setTagFilter] = useState(existing?.trace_tag_filter || "");
  const [traceLimit, setTraceLimit] = useState(existing?.trace_limit || 100);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    const body = {
      project: project.id,
      langfuse_host: host,
      langfuse_public_key: publicKey,
      trace_name_filter: nameFilter || null,
      trace_tag_filter: tagFilter || null,
      trace_limit: traceLimit,
    };
    if (secretKey) body.langfuse_secret_key = secretKey;

    let result;
    if (existing) {
      result = await api.callApi("updateLangfuseStorage", {
        params: { pk: existing.id },
        body,
      });
    } else {
      body.langfuse_secret_key = secretKey;
      result = await api.callApi("createLangfuseStorage", { body });
    }

    if (result?.error) {
      setError(result.response?.detail || "Failed to save configuration");
      setSaving(false);
      return;
    }

    setSaving(false);
    onSave?.();
    onClose?.();
  };

  return (
    <div className={rootClass.elem("form-modal").toClassName()}>
      <div className={rootClass.elem("field").toClassName()}>
        <label className={rootClass.elem("label").toClassName()}>Langfuse Host</label>
        <input
          className={rootClass.elem("input").toClassName()}
          type="text"
          value={host}
          onChange={(e) => setHost(e.target.value)}
          placeholder="https://cloud.langfuse.com"
        />
      </div>

      <div className={rootClass.elem("row").toClassName()}>
        <div className={rootClass.elem("field").toClassName()}>
          <label className={rootClass.elem("label").toClassName()}>Public Key</label>
          <input
            className={rootClass.elem("input").toClassName()}
            type="text"
            value={publicKey}
            onChange={(e) => setPublicKey(e.target.value)}
            placeholder="pk-lf-..."
          />
        </div>
        <div className={rootClass.elem("field").toClassName()}>
          <label className={rootClass.elem("label").toClassName()}>
            Secret Key {existing && "(leave empty to keep current)"}
          </label>
          <input
            className={rootClass.elem("input").toClassName()}
            type="password"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            placeholder={existing ? "••••••••" : "sk-lf-..."}
          />
        </div>
      </div>

      <div className={rootClass.elem("row").toClassName()}>
        <div className={rootClass.elem("field").toClassName()}>
          <label className={rootClass.elem("label").toClassName()}>Trace Name Filter</label>
          <input
            className={rootClass.elem("input").toClassName()}
            type="text"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
            placeholder="Optional"
          />
        </div>
        <div className={rootClass.elem("field").toClassName()}>
          <label className={rootClass.elem("label").toClassName()}>Trace Tag Filter</label>
          <input
            className={rootClass.elem("input").toClassName()}
            type="text"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            placeholder="Optional"
          />
        </div>
      </div>

      <div className={rootClass.elem("field").toClassName()}>
        <label className={rootClass.elem("label").toClassName()}>Max Traces</label>
        <input
          className={rootClass.elem("input").toClassName()}
          type="number"
          value={traceLimit}
          onChange={(e) => setTraceLimit(Number(e.target.value))}
          min={1}
          max={10000}
        />
        <span className={rootClass.elem("hint").toClassName()}>Max traces to import per sync (1-10000)</span>
      </div>

      {error && <div className={rootClass.elem("error").toClassName()}>{error}</div>}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Button look="outlined" onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} waiting={saving}>
          {existing ? "Update" : "Save"}
        </Button>
      </div>
    </div>
  );
};

export const IntegrationsSettings = () => {
  const api = useAPI();
  const { project } = useProject();
  const [storage, setStorage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);
  const configModalRef = useRef();

  const fetchStorage = useCallback(async () => {
    if (!project?.id) return;
    setLoading(true);
    const result = await api.callApi("langfuseStorages", {
      params: { project: project.id },
    });
    if (result && !result.error) {
      const storages = Array.isArray(result) ? result : result.results || [];
      setStorage(storages.length > 0 ? storages[0] : null);
    }
    setLoading(false);
  }, [project?.id]);

  useEffect(() => {
    fetchStorage();
  }, [fetchStorage]);

  const handleSync = useCallback(async () => {
    if (!storage) return;
    setSyncing(true);
    setMessage(null);
    const result = await api.callApi("syncLangfuseStorage", {
      params: { pk: storage.id },
    });
    if (result?.error) {
      setMessage({ type: "error", text: result.response?.detail || "Sync failed" });
    } else {
      setMessage({ type: "success", text: `Sync complete! ${result?.tasks_created || 0} new tasks imported.` });
      fetchStorage();
    }
    setSyncing(false);
  }, [storage, fetchStorage]);

  const handleDelete = useCallback(async () => {
    if (!storage) return;
    if (!window.confirm("Remove Langfuse integration? This won't delete already imported tasks.")) return;
    await api.callApi("deleteLangfuseStorage", {
      params: { pk: storage.id },
    });
    setStorage(null);
    setMessage(null);
  }, [storage]);

  const openConfigModal = useCallback(() => {
    configModalRef.current = modal({
      title: storage ? "Edit Langfuse Connection" : "Connect Langfuse",
      style: { width: 560 },
      body: () => (
        <LangfuseConfigModal
          existing={storage}
          project={project}
          onSave={() => fetchStorage()}
          onClose={() => configModalRef.current?.close()}
        />
      ),
    });
  }, [storage, project, fetchStorage]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
        <Spinner size={36} />
      </div>
    );
  }

  return (
    <div className={rootClass.toClassName()}>
      <div className={rootClass.elem("header").toClassName()}>
        <h2 className={rootClass.elem("title").toClassName()}>Integrations</h2>
        <p className={rootClass.elem("description").toClassName()}>
          Connect external services to import and sync data with this project
        </p>
      </div>

      <div className={rootClass.elem("card").toClassName()}>
        <div className={rootClass.elem("card-header").toClassName()}>
          <div className={rootClass.elem("card-info").toClassName()}>
            <div className={rootClass.elem("card-logo").toClassName()}>LF</div>
            <div>
              <h3 className={rootClass.elem("card-title").toClassName()}>Langfuse</h3>
              <p className={rootClass.elem("card-subtitle").toClassName()}>
                Import LLM traces as annotation tasks
              </p>
            </div>
          </div>
          <div className={rootClass.elem("card-actions").toClassName()}>
            {storage && (
              <>
                <Button size="small" look="outlined" onClick={handleSync} waiting={syncing}>
                  {syncing ? "Syncing..." : "Sync Now"}
                </Button>
                <Button size="small" look="outlined" onClick={openConfigModal}>
                  Edit
                </Button>
                <Button size="small" look="outlined" variant="negative" onClick={handleDelete}>
                  Remove
                </Button>
              </>
            )}
            {!storage && (
              <Button size="small" onClick={openConfigModal}>
                Connect
              </Button>
            )}
          </div>
        </div>

        <div className={rootClass.elem("card-body").toClassName()}>
          {storage ? (
            <>
              <div className={rootClass.elem("status").toClassName()}>
                <span className={rootClass.elem("status-dot").mod({ connected: true }).toClassName()} />
                <span className={rootClass.elem("status-text").toClassName()}>Connected</span>
              </div>
              <div className={rootClass.elem("details").toClassName()}>
                <span className={rootClass.elem("detail-label").toClassName()}>Host</span>
                <span className={rootClass.elem("detail-value").toClassName()}>{storage.langfuse_host}</span>

                <span className={rootClass.elem("detail-label").toClassName()}>Public Key</span>
                <span className={rootClass.elem("detail-value").toClassName()}>{storage.langfuse_public_key}</span>

                {storage.trace_name_filter && (
                  <>
                    <span className={rootClass.elem("detail-label").toClassName()}>Name Filter</span>
                    <span className={rootClass.elem("detail-value").toClassName()}>{storage.trace_name_filter}</span>
                  </>
                )}

                {storage.trace_tag_filter && (
                  <>
                    <span className={rootClass.elem("detail-label").toClassName()}>Tag Filter</span>
                    <span className={rootClass.elem("detail-value").toClassName()}>{storage.trace_tag_filter}</span>
                  </>
                )}

                <span className={rootClass.elem("detail-label").toClassName()}>Max Traces</span>
                <span className={rootClass.elem("detail-value").toClassName()}>{storage.trace_limit}</span>

                {storage.last_sync && (
                  <>
                    <span className={rootClass.elem("detail-label").toClassName()}>Last Sync</span>
                    <span className={rootClass.elem("detail-value").toClassName()}>
                      {new Date(storage.last_sync).toLocaleString()}
                    </span>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className={rootClass.elem("empty").toClassName()}>
              <p className={rootClass.elem("empty-text").toClassName()}>
                No Langfuse connection configured. Connect your Langfuse project to import LLM traces as annotation tasks.
              </p>
            </div>
          )}

          {message && (
            <div
              className={rootClass.elem(message.type === "error" ? "error" : "success").toClassName()}
              style={{ marginTop: 16 }}
            >
              {message.text}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

IntegrationsSettings.title = "Integrations";
IntegrationsSettings.path = "/integrations";
