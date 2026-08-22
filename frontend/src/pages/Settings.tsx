import { useState } from "react";
import { motion } from "framer-motion";
import { Save, RefreshCw, Cpu, Sparkles } from "lucide-react";
import { useConfig, usePutConfig } from "../hooks/api";
import { useStore, useToast } from "../store";
import type { Json } from "../api/client";

export default function Settings() {
  const toast = useToast();
  const query = useConfig();
  const config = useStore((s) => s.config);
  const setConfig = useStore((s) => s.setConfig);
  const put = usePutConfig();

  const [text, setText] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  // Seed the editor when the query resolves with fresh config.
  const [seededKey, setSeededKey] = useState<string>("");
  const key = String(query.dataUpdatedAt);
  if (key !== seededKey && query.data) {
    setText(JSON.stringify(query.data, null, 2));
    setSeededKey(key);
    setDirty(false);
  }

  const save = async () => {
    try {
      const parsed = JSON.parse(text) as Json;
      const res = await put.mutateAsync(parsed);
      setConfig(res);
      setText(JSON.stringify(res, null, 2));
      setDirty(false);
      toast.success("Config saved.");
    } catch (err) {
      toast.error(`Invalid JSON or save failed: ${String(err)}`);
    }
  };

  const reload = () => {
    query.refetch();
    toast.info("Reloading config…");
  };

  const provider =
    (config?.model as Json | undefined)?.current_provider ??
    (config?.model as Json | undefined)?.last_provider ??
    "—";
  const profileKeys = config?.prompt_profiles
    ? Object.keys(
        ((config.prompt_profiles as Json).profiles as Json) ?? {}
      )
    : [];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Settings</h2>
        <p className="text-sm text-text-dim">
          View and edit the engine configuration (saved to config.json on the
          backend).
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Cpu size={14} /> Provider
          </div>
          <div className="text-sm">{String(provider)}</div>
        </div>
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Sparkles size={14} /> Prompt profiles
          </div>
          <div className="text-sm">
            {profileKeys.length ? profileKeys.join(", ") : "—"}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-bg-elev p-4">
        <label className="mb-2 block text-xs font-medium text-text-dim">
          Raw config (JSON)
        </label>
        <textarea
          className="h-80 w-full rounded-md border border-border bg-bg px-3 py-2 font-mono text-xs"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setDirty(true);
          }}
        />
        <div className="mt-3 flex items-center gap-2">
          <button
            className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-2 disabled:opacity-50"
            onClick={save}
            disabled={put.isPending || !dirty}
          >
            <Save size={16} /> Save config
          </button>
          <button
            className="flex items-center gap-2 rounded-md border border-border bg-bg-elev-2 px-3 py-2 text-sm hover:bg-bg"
            onClick={reload}
          >
            <RefreshCw size={14} /> Reload
          </button>
          {dirty && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-xs text-warn"
            >
              Unsaved changes
            </motion.span>
          )}
        </div>
      </div>
    </div>
  );
}
