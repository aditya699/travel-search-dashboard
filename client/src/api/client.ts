// Typed calls to the FastAPI server. Every call carries the viewer's email, which the
// server uses for row-level security (the same user_access table Power BI uses).

import type {
  CheapestFare,
  LeadTimePoint,
  Quality,
  Route,
  SiteScore,
  Summary,
  TrendPoint,
  User,
} from "./types";

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, email?: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: email ? { "X-User-Email": email } : undefined,
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is the server running?`, 0);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? `${response.status} ${response.statusText}`, response.status);
  }
  return (await response.json()) as T;
}

const q = (route: string) => `?route=${encodeURIComponent(route)}`;

export const api = {
  users: () => get<User[]>("/api/users"),
  routes: (email: string) => get<Route[]>("/api/routes", email),
  summary: (email: string) => get<Summary>("/api/summary", email),
  cheapest: (email: string, route: string) => get<CheapestFare[]>(`/api/cheapest${q(route)}`, email),
  trend: (email: string, route: string) => get<TrendPoint[]>(`/api/trend${q(route)}`, email),
  leadTime: (email: string, route: string) => get<LeadTimePoint[]>(`/api/lead-time${q(route)}`, email),
  sites: (email: string) => get<SiteScore[]>("/api/sites", email),
  quality: (email: string) => get<Quality>("/api/quality", email),
};
