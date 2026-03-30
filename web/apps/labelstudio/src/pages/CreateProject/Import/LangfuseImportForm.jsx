import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Select } from "@humansignal/ui";
import { Spinner } from "../../../components";
import { useAPI } from "../../../providers/ApiProvider";
import { cn } from "../../../utils/bem";
import "./LangfuseImportForm.prefix.css";

const rootClass = cn("langfuse-import");

export const LangfuseImportForm = ({ project, onComplete, onCancel }) => {
  const api = useAPI();

  const [status, setStatus] = useState(null);
  const [queues, setQueues] = useState([]);
  const [selectedQueue, setSelectedQueue] = useState("");
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const statusRes = await api.callApi("langfuseStatus");
        if (cancelled) return;
        setStatus(statusRes);

        if (statusRes?.connected) {
          const queuesRes = await api.callApi("langfuseQueues");
          if (cancelled) return;
          setQueues(queuesRes?.data || []);
        }
      } catch (e) {
        if (!cancelled) setError("Failed to check Langfuse connection");
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [api]);

  const handleImport = useCallback(async () => {
    if (!selectedQueue) return;
    setError(null);
    setResult(null);
    setImporting(true);
    try {
      const res = await api.callApi("langfuseQueueImport", {
        body: {
          queue_id: selectedQueue,
          project: project.id,
        },
      });
      if (res?.error) {
        setError(res.response?.detail || "Import failed");
      } else {
        setResult(res);
        if (res.created > 0) {
          setTimeout(() => onComplete?.(), 2000);
        }
      }
    } catch (e) {
      setError("Import failed");
    }
    setImporting(false);
  }, [api, project, selectedQueue, onComplete]);

  const queueOptions = useMemo(
    () =>
      queues.map((q) => ({
        value: q.id,
        label: q.name + (q.description ? ` — ${q.description}` : ""),
      })),
    [queues],
  );

  const selectedQueueInfo = queues.find((q) => q.id === selectedQueue);

  if (loading) {
    return (
      <div className={rootClass.toClassName()}>
        <div className={rootClass.elem("loading").toClassName()}>
          <Spinner size={24} />
          <span>Checking Langfuse connection...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={rootClass.toClassName()}>
      <div className={rootClass.elem("header").toClassName()}>
        <div className={rootClass.elem("logo").toClassName()}>LF</div>
        <div>
          <h3 className={rootClass.elem("title").toClassName()}>Import from Langfuse</h3>
          <p className={rootClass.elem("subtitle").toClassName()}>
            Import traces from an annotation queue into this project
          </p>
        </div>
      </div>

      <div className={rootClass.elem("status-bar").toClassName()}>
        <span
          className={rootClass
            .elem("status-dot")
            .mod({ connected: status?.connected })
            .toClassName()}
        />
        <span className={rootClass.elem("status-text").toClassName()}>
          {status?.connected
            ? `Connected to ${status.host}`
            : status?.configured
              ? `Connection failed: ${status.message}`
              : "Not configured — set LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY in environment"}
        </span>
      </div>

      {status?.connected && (
        <div className={rootClass.elem("form").toClassName()}>
          <div className={rootClass.elem("field").toClassName()}>
            {queues.length === 0 ? (
              <>
                <label className={rootClass.elem("label").toClassName()}>
                  Annotation Queue
                </label>
                <p className={rootClass.elem("hint").toClassName()}>
                  No annotation queues found. Create one in Langfuse first.
                </p>
              </>
            ) : (
              <Select
                label="Annotation Queue"
                options={queueOptions}
                value={selectedQueue || undefined}
                placeholder="Select a queue..."
                onChange={(val) => {
                  setSelectedQueue(val);
                  setResult(null);
                  setError(null);
                }}
              />
            )}
          </div>

          {selectedQueueInfo && (
            <div className={rootClass.elem("queue-info").toClassName()}>
              <span>Queue: <strong>{selectedQueueInfo.name}</strong></span>
              {selectedQueueInfo.description && (
                <span> — {selectedQueueInfo.description}</span>
              )}
            </div>
          )}

          {error && (
            <div className={rootClass.elem("error").toClassName()}>{error}</div>
          )}
          {result && (
            <div className={rootClass.elem("success").toClassName()}>
              Imported {result.created} tasks
              {result.skipped > 0 && `, ${result.skipped} already existed`}
              {" "}(total {result.total} traces in queue)
              {result.label_config_generated && (
                <div className={rootClass.elem("config-notice").toClassName()}>
                  Label config auto-generated from {result.score_configs_count} Langfuse score config(s).
                </div>
              )}
            </div>
          )}

          <div className={rootClass.elem("actions").toClassName()}>
            <Button
              onClick={handleImport}
              disabled={!selectedQueue || importing}
              waiting={importing}
            >
              {importing ? (
                <>
                  <Spinner size={16} /> Importing...
                </>
              ) : (
                "Import from Queue"
              )}
            </Button>
            {onCancel && (
              <Button look="outlined" variant="neutral" onClick={onCancel}>
                Back
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
