import { useState } from "react";
import { motion } from "framer-motion";
import { Save, Trash2, FolderOpen, RefreshCw } from "lucide-react";
import {
  useSessions,
  useSaveSession,
  useDeleteSession,
  useLoadSession,
} from "../hooks/api";
import { useToast } from "../store";
import { SkeletonRows } from "../components/Skeleton";

function sessionId(s: { name?: string; path?: string }): string {
  return String(s.name ?? s.path ?? "");
}

export default function Sessions() {
  const toast = useToast();
  const query = useSessions();
  const save = useSaveSession();
  const del = useDeleteSession();
  const load = useLoadSession();
  const [notice, setNotice] = useState<string | null>(null);

  const sessions = query.data?.sessions ?? [];

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Sessions</h2>
          <p className="text-sm text-text-dim">
            Save, restore, and delete staging sessions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SkeletonRows rows={1} className="!space-y-0" />
        </div>
        <div className="overflow-x-auto rounded-lg border border-border bg-bg-elev p-4">
          <SkeletonRows rows={5} />
        </div>
      </div>
    );
  }

  const onSave = async () => {
    setNotice(null);
    try {
      const res = await save.mutateAsync({});
      setNotice(`Saved session: ${res.path}`);
      toast.success("Session saved.");
    } catch (err) {
      toast.error(String(err));
    }
  };

  const onLoad = async (id: string) => {
    setNotice(null);
    try {
      const res = await load.mutateAsync(id);
      setNotice(`Loaded: ${res.asset_count} assets`);
      toast.success("Session loaded.");
    } catch (err) {
      toast.error(String(err));
    }
  };

  const onDelete = async (id: string) => {
    try {
      await del.mutateAsync(id);
      toast.success("Session deleted.");
    } catch (err) {
      toast.error(String(err));
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Sessions</h2>
        <p className="text-sm text-text-dim">
          Save, restore, and delete staging sessions.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-2"
          onClick={onSave}
          disabled={save.isPending}
        >
          <Save size={16} /> Save current session
        </button>
        <button
          className="flex items-center gap-2 rounded-md border border-border bg-bg-elev-2 px-3 py-2 text-sm hover:bg-bg"
          onClick={() => query.refetch()}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {notice && (
        <div className="rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
          {notice}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-border bg-bg-elev">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Session
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Modified
              </th>
              <th className="px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const id = sessionId(s);
              return (
                <motion.tr
                  key={id}
                  className="border-b border-border/60"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <td className="px-3 py-1.5">
                    <span className="flex items-center gap-2">
                      <FolderOpen size={14} className="text-text-dim" />
                      {id}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-text-dim">
                    {String(s.modified ?? "")}
                  </td>
                  <td className="px-3 py-1.5">
                    <div className="flex justify-end gap-2">
                      <button
                        className="flex items-center gap-1 rounded-md border border-border bg-bg-elev-2 px-2.5 py-1 text-xs hover:bg-bg"
                        onClick={() => onLoad(id)}
                        disabled={load.isPending}
                      >
                        Load
                      </button>
                      <button
                        className="flex items-center gap-1 rounded-md border border-danger/40 bg-danger/10 px-2.5 py-1 text-xs text-danger hover:bg-danger/20"
                        onClick={() => onDelete(id)}
                        disabled={del.isPending}
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>
                  </td>
                </motion.tr>
              );
            })}
            {sessions.length === 0 && (
              <tr>
                <td
                  colSpan={3}
                  className="px-3 py-6 text-center text-text-dim"
                >
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
