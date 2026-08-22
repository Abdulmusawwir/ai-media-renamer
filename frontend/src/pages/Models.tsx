import { motion } from "framer-motion";
import { Download, Cpu, Boxes } from "lucide-react";
import { useModels, useDownloadModel } from "../hooks/api";
import { useToast } from "../store";

export default function Models() {
  const toast = useToast();
  const query = useModels();
  const download = useDownloadModel();

  const data = query.data;

  const onDownload = async (name: string) => {
    try {
      const res = await download.mutateAsync(name);
      toast.info(`Download accepted: ${String(res.detail ?? res.model ?? "")}`);
    } catch (err) {
      toast.error(String(err));
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Models</h2>
        <p className="text-sm text-text-dim">
          Available providers and models. Downloads are handled by the backend
          setup tooling.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Cpu size={14} /> Current provider
          </div>
          <div className="text-sm">{data?.current_provider || "—"}</div>
        </div>
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Boxes size={14} /> Providers
          </div>
          <div className="text-sm">
            {(data?.providers ?? []).join(", ") || "—"}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-bg-elev">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Provider
              </th>
              <th className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Model
              </th>
              <th className="px-3 py-2 text-right text-[11px] font-semibold uppercase tracking-wide text-text-dim">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {(data?.catalog ?? []).map((m, i) => (
              <motion.tr
                key={`${m.provider}-${m.name}-${i}`}
                className="border-b border-border/60"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                <td className="px-3 py-1.5">{m.provider}</td>
                <td className="px-3 py-1.5">{m.name}</td>
                <td className="px-3 py-1.5">
                  <div className="flex justify-end">
                    <button
                      className="flex items-center gap-1 rounded-md border border-border bg-bg-elev-2 px-2.5 py-1 text-xs hover:bg-bg"
                      onClick={() => onDownload(m.name)}
                      disabled={download.isPending}
                    >
                      <Download size={13} /> Download
                    </button>
                  </div>
                </td>
              </motion.tr>
            ))}
            {(data?.catalog ?? []).length === 0 && (
              <tr>
                <td
                  colSpan={3}
                  className="px-3 py-6 text-center text-text-dim"
                >
                  No models in catalog.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && (data.models ?? []).length > 0 && (
        <div className="rounded-lg border border-border bg-bg-elev p-4">
          <label className="mb-1 block text-xs font-medium text-text-dim">
            Available models (current provider)
          </label>
          <div className="text-sm text-text-dim">
            {(data.models ?? []).join(", ")}
          </div>
        </div>
      )}
    </div>
  );
}
