import { PageHeader } from "../components/PageHeader";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { GitCommit, Undo2, Download, ArrowLeft } from "lucide-react";
import { useStaging, useCommit, useRollback, downloadStagingCsv } from "../hooks/api";
import { useStore, useToast } from "../store";

export default function Commit() {
  const navigate = useNavigate();
  const toast = useToast();
  const query = useStaging();
  const commitMut = useCommit();
  const rollbackMut = useRollback();
  const settings = useStore((s) => s.analysisSettings);

  const rows = query.data?.assets ?? [];
  const [results, setResults] = useState<string[] | null>(null);

  const doCommit = async () => {
    if (rows.length === 0) {
      toast.error("Nothing staged to commit.");
      return;
    }
    setResults(null);
    try {
      const res = await commitMut.mutateAsync({
        assets: rows,
        sort_folders: settings.sort_folders,
        skip_rename: settings.skip_rename,
        skip_metadata: settings.skip_metadata,
      });
      setResults(res.results);
      toast.success(`Committed ${res.committed} asset(s).`);
    } catch (err) {
      toast.error(String(err));
    }
  };

  const doRollback = async () => {
    setResults(null);
    try {
      await rollbackMut.mutateAsync();
      toast.success("Rolled back last batch.");
    } catch (err) {
      toast.error(String(err));
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        icon={GitCommit}
        title="Commit & Export"
        description="Persist staged assets to disk (rename + metadata) or roll back the last batch."
        action={
          <button className="ui-btn ui-btn-secondary" onClick={() => navigate("/staging")}>
            <ArrowLeft size={14} /> Back to Staging
          </button>
        }
      />

      <div className="ui-surface">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            className="ui-btn ui-btn-primary"
            onClick={doCommit}
            disabled={commitMut.isPending || rows.length === 0}
          >
            <GitCommit size={16} />
            {commitMut.isPending ? "Working…" : "Commit"}
          </button>
          <button
            className="ui-btn ui-btn-danger"
            onClick={doRollback}
            disabled={rollbackMut.isPending}
          >
            <Undo2 size={16} /> Rollback last batch
          </button>
          <button
            className="ui-btn ui-btn-secondary"
            onClick={downloadStagingCsv}
            disabled={rows.length === 0}
          >
            <Download size={14} /> Export CSV
          </button>
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-text-dim">
          <span>Sort into folders: {settings.sort_folders ? "on" : "off"}</span>
          <span>Skip rename: {settings.skip_rename ? "on" : "off"}</span>
          <span>Skip metadata: {settings.skip_metadata ? "on" : "off"}</span>
        </div>
      </div>

      <div className="ui-scroll overflow-x-auto rounded-lg border border-border bg-bg-elev">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Original
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Proposed
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Category
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.original_name + i} className="border-b border-border/60">
                <td className="px-3 py-1.5 text-text-dim">{r.original_name}</td>
                <td className="px-3 py-1.5">{r.staged_name}</td>
                <td className="px-3 py-1.5">{r.category}</td>
                <td className="px-3 py-1.5">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                      r.commit_status === "committed"
                        ? "bg-ok/15 text-ok"
                        : r.commit_status === "failed"
                        ? "bg-danger/15 text-danger"
                        : "bg-warn/15 text-warn"
                    }`}
                  >
                    {r.commit_status ?? "pending"}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <div className="ui-empty">
                    <span className="ui-empty-icon"><GitCommit size={18} /></span>
                    <span>Nothing is staged for commit yet.</span>
                    <button className="ui-btn ui-btn-secondary ui-empty-action" onClick={() => navigate("/staging")}>
                      Back to Staging
                    </button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {results && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="ui-surface"
        >
          <label className="mb-2 block text-xs font-medium text-text-dim">
            Commit results
          </label>
          <div className="h-44 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-bg p-2 font-mono text-xs leading-relaxed text-text-dim">
            {results.join("\n")}
          </div>
        </motion.div>
      )}
    </div>
  );
}
