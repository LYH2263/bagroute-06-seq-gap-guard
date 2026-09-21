export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
      else if (body) detail = JSON.stringify(body.detail ?? body);
    } catch {
      const text = await res.text();
      if (text) detail = text;
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** 站点变更后通知全局珠串时间线刷新。 */
export function notifyStopsChanged() {
  window.dispatchEvent(new Event("bagroute:stops-changed"));
}
