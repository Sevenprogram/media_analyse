import React from "react";
import { api } from "../utils/api";

export interface UseEndpointOptions {
  enabled?: boolean;
}

export function useEndpoint<T>(path: string, fallback: T, options?: UseEndpointOptions) {
  const enabled = options?.enabled ?? true;
  const [data, setData] = React.useState<T>(fallback);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const reload = React.useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [enabled, path]);

  React.useEffect(() => {
    if (!enabled) return;
    void reload();
  }, [enabled, reload]);

  return { data, error, loading, reload };
}
