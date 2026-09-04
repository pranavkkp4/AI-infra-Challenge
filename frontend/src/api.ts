import { useEffect, useState } from "react";

export const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";
const OPERATOR_KEY = "civicops-operator-key";

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function apiPatch<T>(path: string, payload: object): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as T;
}

export function setOperatorKey(value: string): void {
  window.sessionStorage.setItem(OPERATOR_KEY, value);
}

export async function downloadReport(): Promise<void> {
  const response = await fetch(`${API_URL}/reports/maintenance.md`, { headers: authHeaders() });
  if (!response.ok) throw new Error(await responseError(response));
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "PM_INSIGHT_REPORT.md";
  anchor.click();
  URL.revokeObjectURL(url);
}

function authHeaders(): Record<string, string> {
  const key = window.sessionStorage.getItem(OPERATOR_KEY);
  return key ? { "X-CivicOps-Key": key } : {};
}

export function useApi<T>(path: string | null): ApiState<T> {
  const [state, setState] = useState<Omit<ApiState<T>, "reload">>({
    data: null,
    loading: Boolean(path),
    error: null,
  });
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState((current) => ({ ...current, loading: true, error: null }));
    fetch(`${API_URL}${path}`, { signal: controller.signal, headers: authHeaders() })
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response));
        return response.json() as Promise<T>;
      })
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({ data: null, loading: false, error: String(error) });
      });
    return () => controller.abort();
  }, [path, revision]);

  return { ...state, reload: () => setRevision((value) => value + 1) };
}
