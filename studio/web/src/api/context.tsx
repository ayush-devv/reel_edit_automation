import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { Api } from "./api";
import { createHttpApi } from "./http";
import { createMockApi } from "./mock/mockApi";
import { getMockMode } from "./token";

const ApiContext = createContext<Api | null>(null);

export function defaultApi(): Api {
  const mock = getMockMode();
  return mock ? createMockApi({ engineDown: mock === "down" }) : createHttpApi();
}

export function ApiProvider({ api, children }: { api?: Api; children: ReactNode }) {
  const value = useMemo(() => api ?? defaultApi(), [api]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi outside ApiProvider");
  return api;
}
