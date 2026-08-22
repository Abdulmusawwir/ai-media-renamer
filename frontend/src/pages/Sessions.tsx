import { useEffect, useState } from "react";
import {
  deleteSession,
  getStaging,
  listSessions,
  loadSession,
  saveSession,
  type SessionInfo,
} from "../api/client";
import { useStore } from "../store";

function sessionId(s: SessionInfo): string {
  return String(s.name ?? s.path ?? "");
}

export default function Sessions() {
  const { setStaged } = useStore();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refresh = async () => {
    try {
      const res = await listSessions();
      setSessions(res.sessions);
    } catch (err) {
      setError(String(err));
    }
  };

  const doSave = async () => {
    try {
      const res = await saveSession({});
      setNotice(`Saved session: ${res.path}`);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  const doLoad = async (id: string) => {
    try {
      const res = await loadSession(id);
      const staging = await getStaging();
      setStaged(staging.assets);
      setNotice(`Loaded: ${res.asset_count} assets`);
    } catch (err) {
      setError(String(err));
    }
  };

  const doDelete = async (id: string) => {
    try {
      await deleteSession(id);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="page">
      <h2>Sessions</h2>
      <p className="page-sub">Save, restore, and delete staging sessions.</p>

      {error && <p className="badge failed">{error}</p>}
      {notice && <p className="badge ok">{notice}</p>}

      <div className="card">
        <button onClick={doSave}>Save current session</button>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Modified</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const id = sessionId(s);
              return (
                <tr key={id}>
                  <td>{id}</td>
                  <td className="muted">{String(s.modified ?? "")}</td>
                  <td className="row" style={{ margin: 0, justifyContent: "flex-end" }}>
                    <button className="secondary" onClick={() => doLoad(id)}>
                      Load
                    </button>
                    <button className="danger" onClick={() => doDelete(id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {sessions.length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  No saved sessions.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
