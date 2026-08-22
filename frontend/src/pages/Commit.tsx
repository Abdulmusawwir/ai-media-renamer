import { useEffect, useState } from "react";
import {
  commit,
  exportStagingCsv,
  getStaging,
  rollback,
  type StagedAsset,
} from "../api/client";
import { useStore } from "../store";

export default function Commit() {
  const { staged, setStaged } = useStore();
  const [rows, setRows] = useState<StagedAsset[]>([]);
  const [results, setResults] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = async () => {
    try {
      const res = await getStaging();
      setStaged(res.assets);
      setRows(res.assets);
    } catch (err) {
      setError(String(err));
    }
  };

  const doCommit = async () => {
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const res = await commit({ assets: rows });
      setResults(res.results);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const doRollback = async () => {
    setBusy(true);
    setError(null);
    try {
      await rollback();
      setResults(null);
      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    try {
      const csv = await exportStagingCsv();
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "staging.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="page">
      <h2>Commit & Export</h2>
      <p className="page-sub">
        Persist staged assets to disk (rename + metadata) or roll back the last
        batch.
      </p>

      {error && <p className="badge failed">{error}</p>}

      <div className="card">
        <div className="row">
          <button onClick={doCommit} disabled={busy || rows.length === 0}>
            {busy ? "Working…" : "Commit"}
          </button>
          <button className="danger" onClick={doRollback} disabled={busy}>
            Rollback last batch
          </button>
          <button className="secondary" onClick={doExport} disabled={rows.length === 0}>
            Export CSV
          </button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Original</th>
              <th>Proposed</th>
              <th>Category</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.original_name + i}>
                <td className="muted">{r.original_name}</td>
                <td>{r.staged_name}</td>
                <td>{r.category}</td>
                <td>
                  <span
                    className={
                      r.commit_status === "committed"
                        ? "badge ok"
                        : r.commit_status === "failed"
                        ? "badge failed"
                        : "badge pending"
                    }
                  >
                    {r.commit_status ?? "pending"}
                  </span>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  Nothing staged.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {results && (
        <div className="card">
          <label>Commit results</label>
          <div className="log">{results.join("\n")}</div>
        </div>
      )}
    </div>
  );
}
