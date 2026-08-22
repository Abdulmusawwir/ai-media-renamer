import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  bulkUpdateStaging,
  exportStagingCsv,
  getStaging,
  importStagingCsv,
  putStaging,
  type StagedAsset,
} from "../api/client";
import { useStore } from "../store";

export default function Staging() {
  const navigate = useNavigate();
  const { staged, setStaged } = useStore();
  const [rows, setRows] = useState<StagedAsset[]>([]);
  const [bulkCategory, setBulkCategory] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = async () => {
    try {
      const res = await getStaging();
      setStaged(res.assets);
      setRows(
        res.assets.map((a) => ({ ...a, tags: a.tags ?? [], selected: false }))
      );
    } catch (err) {
      setError(String(err));
    }
  };

  const updateRow = (i: number, patch: Partial<StagedAsset>) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const toggleSelect = (i: number) => {
    setRows((prev) =>
      prev.map((r, idx) => (idx === i ? { ...r, selected: !r.selected } : r))
    );
  };

  const selectedNames = rows.filter((r) => r.selected).map((r) => r.original_name);

  const applyBulk = async () => {
    if (selectedNames.length === 0 || !bulkCategory) {
      setError("Select rows and choose a category first.");
      return;
    }
    try {
      const res = await bulkUpdateStaging({
        selected: selectedNames,
        updates: { category: bulkCategory },
      });
      setNotice(`Applied category to ${res.applied} asset(s).`);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  const save = async () => {
    try {
      const clean = rows.map(({ selected, ...rest }) => rest);
      await putStaging(clean as StagedAsset[]);
      setNotice("Staging saved.");
      await refresh();
    } catch (err) {
      setError(String(err));
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

  const doImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const csv = await file.text();
      const res = await importStagingCsv(csv);
      setNotice(`Imported ${res.imported} asset(s).`);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="page">
      <h2>Staging</h2>
      <p className="page-sub">
        Review and edit AI suggestions before committing to disk.
      </p>

      {error && <p className="badge failed">{error}</p>}
      {notice && <p className="badge ok">{notice}</p>}

      <div className="card">
        <div className="row">
          <select
            value={bulkCategory}
            onChange={(e) => setBulkCategory(e.target.value)}
            style={{ maxWidth: 240 }}
          >
            <option value="">Bulk category…</option>
            {Array.from(
              new Set(rows.map((r) => r.category).filter(Boolean))
            ).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button className="secondary" onClick={applyBulk}>
            Apply to selected
          </button>
          <button className="secondary" onClick={doExport}>
            Export CSV
          </button>
          <label
            className="secondary"
            style={{
              display: "inline-block",
              padding: "8px 14px",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Import CSV
            <input
              type="file"
              accept=".csv"
              onChange={doImport}
              style={{ display: "none" }}
            />
          </label>
          <button className="secondary" onClick={save}>
            Save
          </button>
          <button onClick={() => navigate("/commit")}>Go to Commit →</button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Original</th>
              <th>Proposed filename</th>
              <th>Category</th>
              <th>Tags</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.original_name + i}>
                <td>
                  <input
                    type="checkbox"
                    checked={!!r.selected}
                    onChange={() => toggleSelect(i)}
                  />
                </td>
                <td className="muted">{r.original_name}</td>
                <td>
                  <input
                    type="text"
                    value={r.staged_name}
                    onChange={(e) => updateRow(i, { staged_name: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={r.category}
                    onChange={(e) => updateRow(i, { category: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={(r.tags ?? []).join(", ")}
                    onChange={(e) =>
                      updateRow(i, {
                        tags: e.target.value
                          .split(",")
                          .map((t) => t.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={r.description ?? ""}
                    onChange={(e) =>
                      updateRow(i, { description: e.target.value })
                    }
                  />
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No staged assets. Run an analysis first.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
