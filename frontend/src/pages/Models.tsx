import { PageHeader } from "../components/PageHeader";
import { motion } from "framer-motion";
import { Download, Cpu, Boxes } from "lucide-react";
import { useEnvironment, useModels, useDownloadModel } from "../hooks/api";
import { useToast } from "../store";
import { Skeleton, SkeletonRows, Spinner } from "../components/Skeleton";
import { Tooltip } from "../components/Tooltip";

export default function Models() {
  const toast = useToast();
  const query = useModels();
  const download = useDownloadModel();
  const environment = useEnvironment();

  const data = query.data;
  const serverModels = [
    ...(environment.data?.vision_models ?? []),
    ...(environment.data?.text_models ?? []),
  ];
  const normalise = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, "");
  const isOnServer = (name: string) => {
    const wanted = normalise(name);
    return serverModels.some((model) => {
      const found = normalise(model);
      return found.includes(wanted) || wanted.includes(found);
    });
  };

  const onDownload = async (name: string) => {
    try {
      const res = await download.mutateAsync(name);
      toast.info(`Download accepted: ${String(res.detail ?? res.model ?? "")}`);
    } catch (err) {
      toast.error(String(err));
    }
  };

  if (query.isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader
          icon={Boxes}
          title="Models"
          description="Available providers and models. Downloads are handled by the backend setup tooling."
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
        <div className="ui-scroll overflow-x-auto ui-surface">
          <SkeletonRows rows={4} />
        </div>
      </div>
    );
  }

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
        <div className="ui-surface">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Cpu size={14} /> Current provider
          </div>
          <div className="text-sm">{data?.current_provider || "—"}</div>
        </div>
        <div className="ui-surface">
          <div className="mb-1 flex items-center gap-2 text-xs font-medium text-text-dim">
            <Boxes size={14} /> Providers
          </div>
          <div className="text-sm">
            {(data?.providers ?? []).join(", ") || "—"}
          </div>
        </div>
      </div>

      <div className="ui-scroll overflow-x-auto rounded-lg border border-border bg-bg-elev">
        <table className="ui-table w-full border-collapse text-sm">
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
                <td className="px-3 py-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span>{m.name}</span>
                    {/vl|vision/i.test(m.name) && (
                      <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">
                        Vision
                      </span>
                    )}
                    {isOnServer(m.name) ? (
                      <span className="rounded-full border border-ok/30 bg-ok/10 px-2 py-0.5 text-[10px] font-semibold text-ok">
                        On server
                      </span>
                    ) : (
                      <span className="rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] text-text-dim">
                        Catalog
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-1.5">
                  <div className="flex justify-end">
                    <Tooltip
                      side="left"
                      label={
                        isOnServer(m.name)
                          ? "Already available on the running server"
                          : `Download ${m.name}`
                      }
                    >
                      <button
                        className="ui-btn ui-btn-secondary"
                        onClick={() => onDownload(m.name)}
                        disabled={download.isPending || isOnServer(m.name)}
                      >
                        <Download size={13} /> Download
                      </button>
                    </Tooltip>
                  </div>
                </td>
              </motion.tr>
            ))}
            {(data?.catalog ?? []).length === 0 && (
              <tr>
                <td
                  colSpan={3}
                >
                  <div className="ui-empty">
                    <span className="ui-empty-icon"><Boxes size={18} /></span>
                    <span>No models in catalog. Run setup to install a local model.</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && (data.models ?? []).length > 0 && (
        <div className="ui-surface">
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
