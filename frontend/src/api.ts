import { useEffect, useState } from "react";
import { Capacitor, CapacitorHttp } from "@capacitor/core";

function resolveApiUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }

  if (Capacitor.isNativePlatform()) {
    const configuredBase = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    return `${configuredBase}${url}`;
  }

  return url;
}

export function useApi<T>(url: string | null) {
  const [state, set] = useState<{
    data?: T;
    error?: string;
    loading: boolean;
  }>({
    loading: true,
  });

  useEffect(() => {
    if (!url) {
      set({
        loading: false,
      });
      return;
    }

    const requestUrl = url;
    let cancelled = false;

    async function load() {
      try {
        set((previous) => ({
          loading: true,
          data: previous.data,
        }));

        const finalUrl = resolveApiUrl(requestUrl);

        console.log("API REQUEST:", finalUrl);

        if (Capacitor.isNativePlatform()) {
          const response = await CapacitorHttp.get({
            url: finalUrl,
            headers: {
              Accept: "application/json",
            },
          });

          if (response.status < 200 || response.status >= 300) {
            const detail =
              response.data &&
              typeof response.data === "object" &&
              typeof response.data.detail === "string"
                ? response.data.detail
                : null;

            throw new Error(
              detail ??
                `Nie udało się pobrać danych (${response.status}).`,
            );
          }

          if (!cancelled) {
            set({
              data: response.data as T,
              loading: false,
            });
          }

          return;
        }

        const response = await fetch(finalUrl, {
          headers: {
            Accept: "application/json",
          },
        });

        if (!response.ok) {
          const body = await response.json().catch(() => ({}));

          throw new Error(
            typeof body.detail === "string"
              ? body.detail
              : `Nie udało się pobrać danych (${response.status}).`,
          );
        }

        const data = (await response.json()) as T;

        if (!cancelled) {
          set({
            data,
            loading: false,
          });
        }
      } catch (e) {
        if (cancelled) {
          return;
        }

        console.error("API ERROR:", e);

        const message =
          e instanceof Error
            ? e.message
            : "Nie udało się połączyć z API.";

        set((previous) => ({
          data: previous.data,
          error: message,
          loading: false,
        }));
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [url]);

  return state;
}

export type Dataset = {
  id: string;
  maturity: string;
  research_ready: boolean;
  created_at: string;
};

export type Firm = {
  company_id: string;
  krs: string;
  name: string | null;
  legal_form: string | null;
  years: number;
  first_year: number;
  last_year: number;
};

export type Year = {
  year: number;
  selection_status: string;
  features: Record<string, number | null>;
  missing_reasons: Record<string, string>;
  quality_codes: string[];
};

export type Company = {
  krs: string;
  identity_snapshots: {
    name: string | null;
    legal_form: string | null;
    website: string | null;
  }[];
  years: Year[];
  unit_note: string;
  identity_note: string;
};

export type Summary = {
  observations: number;
  companies: number;
  first_year: number;
  last_year: number;
  unresolved_observations: number;
  years: {
    year: number;
    observations: number;
    selected: number;
  }[];
  cohorts: Record<string, number>;
};

export type Coefficient = {
  coefficient: number | null;
  standard_error: number | null;
  ci95_low: number | null;
  ci95_high: number | null;
  p_value: number | null;
};

export type Estimate = {
  model: string;
  variant: string;
  status: string;
  n_companies: number;
  n_observations: number;
  r_squared: number | null;
  within_r_squared: number | null;
  coefficients: Record<string, Coefficient>;
  error?: string;
};

export type Study = {
  specification: {
    id: string;
    title: string;
    outcome: string;
    exposure: string;
    controls: string[];
    primary_term: string;
    quadratic: boolean;
  };
  estimates: Estimate[];
  sample_flow: Record<string, unknown>;
  primary_test: {
    bh_q_value: number | null;
  };
};

export type Research = {
  run_id: string;
  dataset_id: string;
  causal: boolean;
  provisional_dataset: boolean;
  out_of_sample_validated: boolean;
  studies: Study[];
  protocol: Record<string, unknown>;
};

// ---------------------------------------------------------------------------
// Background job support (Redis Queue)
// ---------------------------------------------------------------------------

export type JobStatus = {
  job_id: string;
  status: "queued" | "started" | "finished" | "failed" | "deferred" | "canceled";
  progress: string | null;
  percent: number | null;
  enqueued_at: string | null;
  started_at: string | null;
  ended_at: string | null;
};

export function useJob(jobId: string | null, pollIntervalMs = 2000) {
  const [state, set] = useState<{
    job?: JobStatus;
    error?: string;
    loading: boolean;
  }>({ loading: !!jobId });

  useEffect(() => {
    if (!jobId) {
      set({ loading: false });
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      try {
        const url = resolveApiUrl(`/api/jobs/${jobId}`);
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(
            typeof body.detail === "string"
              ? body.detail
              : `Błąd pobierania statusu zadania (${response.status}).`,
          );
        }
        const data = (await response.json()) as JobStatus;
        if (!cancelled) {
          set({ job: data, loading: false });
          if (data.status === "finished" || data.status === "failed") {
            if (timer) clearInterval(timer);
          }
        }
      } catch (e) {
        if (!cancelled) {
          set((prev) => ({
            job: prev.job,
            error: e instanceof Error ? e.message : "Błąd połączenia z API.",
            loading: false,
          }));
          if (timer) clearInterval(timer);
        }
      }
    }

    void poll();
    timer = setInterval(poll, pollIntervalMs);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [jobId, pollIntervalMs]);

  return state;
}

export async function submitJob(
  endpoint: string,
  params: Record<string, string | number | null | undefined>,
): Promise<{ job_id: string; status: string }> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") {
      query.set(key, String(value));
    }
  }
  const url = resolveApiUrl(`${endpoint}?${query.toString()}`);
  const response = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Nie udało się zlecić zadania (${response.status}).`,
    );
  }
  return response.json();
}
