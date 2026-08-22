import { useEffect, useState } from "react";
import { downloadModel, listModels, type ModelsResponse } from "../api/client";

export default function Models() {
  const [data, setData] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    listModels()
      .then(setData)
      .catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doDownload = async (name: string) => {
    setError(null);
    setNotice(null);
    try {
      const res = await downloadModel(name);
      setNotice(`Download accepted: ${String(res.detail ?? res.model ?? "")}`);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="page">
      <h2>Models</h2>
      <p className="page-sub">
        Available providers and models. Downloads are handled by the backend
        setup tooling.
      </p>

      {error && <p className="badge failed">{error}</p>}
      {notice && <p className="badge ok">{notice}</p>}

      <div className="card">
        <div className="grid-2">
          <div>
            <label>Current provider</label>
            <div className="muted">{data?.current_provider || "—"}</div>
          </div>
          <div>
            <label>Providers</label>
            <div className="muted">{(data?.providers ?? []).join(", ") || "—"}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Model</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data?.catalog ?? []).map((m, i) => (
              <tr key={`${m.provider}-${m.name}-${i}`}>
                <td>{m.provider}</td>
                <td>{m.name}</td>
                <td className="row" style={{ margin: 0, justifyContent: "flex-end" }}>
                  <button
                    className="secondary"
                    onClick={() => doDownload(m.name)}
                  >
                    Download
                  </button>
                </td>
              </tr>
            ))}
            {(data?.catalog ?? []).length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  No models in catalog.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && (data.models ?? []).length > 0 && (
        <div className="card">
          <label>Available models (current provider)</label>
          <div className="muted">{(data.models ?? []).join(", ")}</div>
        </div>
      )}
    </div>
  );
}
