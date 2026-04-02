import { useCallback, useEffect, useMemo, useState } from "react";
import { Spinner } from "../../../components";
import { useAPI } from "../../../providers/ApiProvider";

export const LangfuseImportForm = ({ project, onImportReady }) => {
  const api = useAPI();

  const [queues, setQueues] = useState([]);
  const [selectedQueue, setSelectedQueue] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const queuesRes = await api.callApi("langfuseQueues");
        if (cancelled) return;
        setQueues(queuesRes?.data || []);
      } catch (e) {
        if (!cancelled) setError("Failed to fetch queues");
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [api]);

  const doImport = useCallback(async () => {
    if (!selectedQueue) return null;
    setError(null);
    try {
      const res = await api.callApi("langfuseQueueImport", {
        body: {
          queue_id: selectedQueue,
          project: project.id,
        },
      });
      if (res?.error) {
        setError(res.response?.detail || "Import failed");
        return null;
      }
      return res;
    } catch (e) {
      setError("Import failed");
      return null;
    }
  }, [api, project, selectedQueue]);

  useEffect(() => {
    onImportReady?.(selectedQueue ? doImport : null);
  }, [selectedQueue, doImport, onImportReady]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 p-12 text-neutral-content-subtle text-body-medium">
        <Spinner size={24} />
        <span>Loading annotation queues...</span>
      </div>
    );
  }

  if (queues.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-center text-neutral-content-subtle">
        <h3 className="text-base font-semibold text-neutral-content mt-3 mb-1">
          No annotation queues found
        </h3>
        <p className="text-body-small">
          Create an annotation queue in Langfuse first, then come back to import.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Select an annotation queue</h2>
        <p className="text-muted-foreground">
          Choose a Langfuse annotation queue to import traces from
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-base">
        {queues.map((q) => {
          const isSelected = selectedQueue === q.id;
          const scoreCount = q.scoreConfigIds?.length || 0;

          return (
            <button
              key={q.id}
              type="button"
              onClick={() => {
                setSelectedQueue(isSelected ? "" : q.id);
                setError(null);
              }}
              className={[
                "relative p-base border-2 rounded-lg transition-all duration-200 text-left min-h-[100px]",
                "flex flex-col gap-tight",
                "hover:border-primary-border-subtle hover:bg-primary-emphasis-subtle",
                "hover:-translate-y-tightest focus:outline-none focus:ring-2 focus:ring-primary-focus-outline focus:ring-offset-2",
                isSelected
                  ? "border-primary-border-subtle bg-primary-emphasis-subtle shadow-sm"
                  : "border-neutral-border",
              ].join(" ")}
              aria-pressed={isSelected}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-body-medium font-medium text-neutral-content">
                  {q.name}
                </h3>
                {isSelected && (
                  <span className="w-5 h-5 rounded-full bg-primary-content text-white flex items-center justify-center text-xs font-bold shrink-0">
                    ✓
                  </span>
                )}
              </div>

              {q.description && (
                <p className="text-body-small text-neutral-content-subtler leading-snug">
                  {q.description}
                </p>
              )}

              {scoreCount > 0 && (
                <div className="mt-auto pt-1">
                  <span className="inline-block px-1.5 py-0.5 rounded text-body-smaller text-neutral-content-subtler bg-neutral-surface border border-neutral-border">
                    {scoreCount} score dimension{scoreCount > 1 ? "s" : ""}
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </div>

      {error && (
        <p className="text-body-small text-negative-content">{error}</p>
      )}
    </div>
  );
};

export const useLangfuseStatus = () => {
  const api = useAPI();
  const [available, setAvailable] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.callApi("langfuseStatus");
        if (!cancelled) setAvailable(res?.connected === true);
      } catch {
        if (!cancelled) setAvailable(false);
      }
      if (!cancelled) setChecked(true);
    })();
    return () => { cancelled = true; };
  }, [api]);

  return { available, checked };
};
