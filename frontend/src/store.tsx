import {
  createContext,
  useContext,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type {
  EnvironmentResponse,
  Json,
  StagedAsset,
} from "./api/client";

interface AnalysisProgress {
  running: boolean;
  processed: number;
  total: number;
  log: string[];
  status: string;
}

interface StoreValue {
  environment: EnvironmentResponse | null;
  setEnvironment: Dispatch<SetStateAction<EnvironmentResponse | null>>;

  config: Json | null;
  setConfig: Dispatch<SetStateAction<Json | null>>;

  staged: StagedAsset[];
  setStaged: Dispatch<SetStateAction<StagedAsset[]>>;

  progress: AnalysisProgress;
  setProgress: Dispatch<SetStateAction<AnalysisProgress>>;
}

const StoreContext = createContext<StoreValue | null>(null);

const initialProgress: AnalysisProgress = {
  running: false,
  processed: 0,
  total: 0,
  log: [],
  status: "",
};

export function StoreProvider({ children }: { children: ReactNode }) {
  const [environment, setEnvironment] = useState<EnvironmentResponse | null>(null);
  const [config, setConfig] = useState<Json | null>(null);
  const [staged, setStaged] = useState<StagedAsset[]>([]);
  const [progress, setProgress] = useState<AnalysisProgress>(initialProgress);

  const value = useMemo<StoreValue>(
    () => ({
      environment,
      setEnvironment,
      config,
      setConfig,
      staged,
      setStaged,
      progress,
      setProgress,
    }),
    [environment, config, staged, progress]
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) {
    throw new Error("useStore must be used within a StoreProvider");
  }
  return ctx;
}
