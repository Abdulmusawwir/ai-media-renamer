import { useEffect, useState } from "react";
import { getConfig, putConfig, type Json } from "../api/client";
import { useStore } from "../store";

export default function Settings() {
  const { config, setConfig } = useStore();
  const [text, setText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then((c) => {
        setConfig(c);
        setText(JSON.stringify(c, null, 2));
      })
      .catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    setError(null);
    setNotice(null);
    try {
      const parsed = JSON.parse(text) as Json;
      const res = await putConfig(parsed);
      setConfig(res);
      setText(JSON.stringify(res, null, 2));
      setNotice("Config saved.");
    } catch (err) {
      setError(`Invalid JSON or save failed: ${String(err)}`);
    }
  };

  const reload = async () => {
    try {
      const c = await getConfig();
      setConfig(c);
      setText(JSON.stringify(c, null, 2));
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="page">
      <h2>Settings</h2>
      <p className="page-sub">
        View and edit the engine configuration (saved to config.json on the
        backend).
      </p>

      {error && <p className="badge failed">{error}</p>}
      {notice && <p className="badge ok">{notice}</p>}

      {config && (
        <div className="card">
          <div className="grid-2">
            <div>
              <label>Provider</label>
              <div className="muted">
                {String(
                  (config.model as Json)?.["current_provider"] ?? "—"
                )}
              </div>
            </div>
            <div>
              <label>Prompt profiles</label>
              <div className="muted">
                {Object.keys((config.prompt_profiles as Json) ?? {}).join(", ") ||
                  "—"}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <label>Raw config (JSON)</label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={20}
          style={{ fontFamily: "ui-monospace, monospace" }}
        />
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={save}>Save config</button>
          <button className="secondary" onClick={reload}>
            Reload
          </button>
        </div>
      </div>
    </div>
  );
}
