import { create } from "zustand";
import type {
  EnvironmentResponse,
  Json,
  StagedAsset,
} from "./api/client";

export interface AnalysisSettings {
  case_style: string;
  max_chars: number;
  language: string;
  sort_folders: boolean;
  skip_rename: boolean;
  skip_metadata: boolean;
}

export const DEFAULT_ANALYSIS_SETTINGS: AnalysisSettings = {
  case_style: "title_case",
  max_chars: 0,
  language: "en",
  sort_folders: true,
  skip_rename: false,
  skip_metadata: false,
};

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface WsProgress {
  running: boolean;
  processed: number;
  total: number;
  log: string[];
  status: string;
}

interface AppState {
  environment: EnvironmentResponse | null;
  config: Json | null;
  categories: string[];
  staged: StagedAsset[];
  analysisSettings: AnalysisSettings;
  toasts: ToastItem[];
  wsProgress: WsProgress;

  setEnvironment: (e: EnvironmentResponse | null) => void;
  setConfig: (c: Json | null) => void;
  setCategories: (cats: string[]) => void;
  setStaged: (s: StagedAsset[]) => void;
  setAnalysisSettings: (s: Partial<AnalysisSettings>) => void;
  pushToast: (kind: ToastKind, message: string) => void;
  dismissToast: (id: number) => void;
  setWsProgress: (p: WsProgress) => void;
}

let toastSeq = 0;

export const useStore = create<AppState>((set) => ({
  environment: null,
  config: null,
  categories: [],
  staged: [],
  analysisSettings: { ...DEFAULT_ANALYSIS_SETTINGS },
  toasts: [],
  wsProgress: { running: false, processed: 0, total: 0, log: [], status: "" },

  setEnvironment: (environment) => set({ environment }),
  setConfig: (config) =>
    set({
      config,
      categories: Array.isArray((config?.allowed_categories as unknown[]) ?? [])
        ? (config?.allowed_categories as string[])
        : [],
    }),
  setCategories: (categories) => set({ categories }),
  setStaged: (staged) => set({ staged }),
  setAnalysisSettings: (s) =>
    set((state) => ({ analysisSettings: { ...state.analysisSettings, ...s } })),
  pushToast: (kind, message) =>
    set((state) => ({
      toasts: [...state.toasts, { id: ++toastSeq, kind, message }],
    })),
  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  setWsProgress: (wsProgress) => set({ wsProgress }),
}));

export function useToast() {
  const pushToast = useStore((s) => s.pushToast);
  return {
    success: (m: string) => pushToast("success", m),
    error: (m: string) => pushToast("error", m),
    info: (m: string) => pushToast("info", m),
  };
}
