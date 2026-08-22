import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  bulkUpdateStaging,
  commit,
  deleteSession,
  downloadModel,
  exportStagingCsv,
  getConfig,
  getEnvironment,
  getStaging,
  importStagingCsv,
  listModels,
  listSessions,
  loadSession,
  putConfig,
  putStaging,
  rollback,
  saveSession,
  type CommitPayload,
  type Json,
  type ModelsResponse,
  type SessionInfo,
  type StagedAsset,
} from "../api/client";

export function useEnvironment() {
  return useQuery({
    queryKey: ["environment"],
    queryFn: getEnvironment,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
  });
}

export function useModels() {
  return useQuery<ModelsResponse>({
    queryKey: ["models"],
    queryFn: listModels,
  });
}

export function useSessions() {
  return useQuery<{ sessions: SessionInfo[] }>({
    queryKey: ["sessions"],
    queryFn: listSessions,
  });
}

export function useStaging() {
  return useQuery({
    queryKey: ["staging"],
    queryFn: getStaging,
  });
}

export function usePutConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Json) => putConfig(patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

export function useBulkUpdateStaging() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { selected: string[]; updates: Json }) =>
      bulkUpdateStaging(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useImportStagingCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (csv: string) => importStagingCsv(csv),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useSaveStaging() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rows: StagedAsset[]) => putStaging(rows),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useCommit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CommitPayload) => commit(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useRollback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => rollback(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useSaveSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (settings: Json) => saveSession(settings),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

export function useLoadSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => loadSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["staging"] });
    },
  });
}

export function useDownloadModel() {
  return useMutation({
    mutationFn: (name: string) => downloadModel(name),
  });
}

export function downloadStagingCsv(): Promise<void> {
  return exportStagingCsv().then((csv) => {
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "staging.csv";
    a.click();
    URL.revokeObjectURL(url);
  });
}

export type { StagedAsset };
