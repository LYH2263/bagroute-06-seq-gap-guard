export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    // FastAPI errors come back as {"detail": "..."} (409/404) or a list of
    // validation issues (422); surface the human reason to callers.
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d))
          .join("；");
      } else {
        detail = JSON.stringify(body);
      }
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
