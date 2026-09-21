import { useCallback, useEffect, useState } from "react";
import { api, notifyStopsChanged } from "../api/client";
type S = { id: number; route_id: number; seq: number; name: string; weight_kg: number; volume_l: number };
type R = { id: number; name: string };

export default function StopsPage() {
  const [routes, setRoutes] = useState<R[]>([]);
  const [rid, setRid] = useState<number | "">("");
  const [rows, setRows] = useState<S[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [editSeq, setEditSeq] = useState<Record<number, string>>({});
  const [form, setForm] = useState({ name: "", weight_kg: "1", volume_l: "2" });

  const load = useCallback((id: number) => {
    api<S[]>(`/stops?route_id=${id}`).then(setRows).catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => { api<R[]>("/routes").then(r => { setRoutes(r); if (r[0]) setRid(r[0].id); }); }, []);
  useEffect(() => {
    if (rid === "") return;
    setErr(""); setMsg("");
    load(rid);
  }, [rid, load]);

  async function addStop() {
    if (rid === "") return;
    if (!form.name.trim()) { setErr("请填写站点名称"); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      await api("/stops", {
        method: "POST",
        body: JSON.stringify({
          route_id: rid,
          name: form.name.trim(),
          weight_kg: Number(form.weight_kg),
          volume_l: Number(form.volume_l),
        }),
      });
      setForm(f => ({ ...f, name: "" }));
      load(rid);
      notifyStopsChanged();
      setMsg(`已追加为 #${rows.length + 1}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function saveSeq(s: S) {
    if (rid === "") return;
    const raw = editSeq[s.id];
    const next = Number(raw);
    if (!raw || !Number.isInteger(next) || next < 1) { setErr("序号必须是不小于 1 的整数"); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      await api(`/stops/${s.id}`, { method: "PATCH", body: JSON.stringify({ seq: next }) });
      setEditSeq(m => { const c = { ...m }; delete c[s.id]; return c; });
      load(rid);
      notifyStopsChanged();
      setMsg("序号已更新，途经站点自动顺延");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function resequence() {
    if (rid === "") return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const out = await api<S[]>(`/routes/${rid}/stops/resequence`, { method: "POST" });
      setRows(out);
      notifyStopsChanged();
      setMsg(`已按现有顺序重排为 1..${out.length}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  return (<>
    <h2>订户点</h2>
    <div className="toolbar">
      <select value={rid} onChange={e => setRid(Number(e.target.value))}>{routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
      <button onClick={resequence} disabled={busy || rows.length === 0}>重排序号 1..n</button>
      <span className="mono" style={{ color: "var(--route-muted)", fontSize: ".8rem" }}>
        同路线序号必须从 1 起连续；新站点追加为 #{rows.length + 1}
      </span>
    </div>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <div className="route-strip">
      {rows.map(s => (
        <div className="stop-chip" key={s.id}>
          <span className="seq">#{s.seq}</span>
          <strong>{s.name}</strong>
          <span className="mono">{s.weight_kg}kg · {s.volume_l}L</span>
        </div>
      ))}
    </div>
    <table className="table">
      <thead><tr><th>序号</th><th>名称</th><th>重量 kg</th><th>体积 L</th><th>操作</th></tr></thead>
      <tbody>
        {rows.map(s => (
          <tr key={s.id}>
            <td className="mono">
              <input
                aria-label={`${s.name} 序号`}
                style={{ width: 70, padding: ".3rem .45rem" }}
                value={editSeq[s.id] ?? String(s.seq)}
                onChange={e => setEditSeq(m => ({ ...m, [s.id]: e.target.value }))}
              />
            </td>
            <td>{s.name}</td>
            <td className="mono">{s.weight_kg}</td>
            <td className="mono">{s.volume_l}</td>
            <td>
              <button
                disabled={busy || editSeq[s.id] === undefined || Number(editSeq[s.id]) === s.seq}
                onClick={() => saveSeq(s)}
                style={{ padding: ".3rem .6rem" }}
              >保存序号</button>
            </td>
          </tr>
        ))}
        {!rows.length && <tr><td colSpan={5}>该路线暂无站点</td></tr>}
      </tbody>
    </table>
    <h2 style={{ marginTop: "1.25rem" }}>新增站点（追加到队尾）</h2>
    <div className="toolbar">
      <input placeholder="站点名称" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
      <input style={{ width: 110 }} aria-label="重量 kg" type="number" step="0.1" value={form.weight_kg} onChange={e => setForm(f => ({ ...f, weight_kg: e.target.value }))} />
      <input style={{ width: 110 }} aria-label="体积 L" type="number" step="0.1" value={form.volume_l} onChange={e => setForm(f => ({ ...f, volume_l: e.target.value }))} />
      <button onClick={addStop} disabled={busy}>追加为 #{rows.length + 1}</button>
    </div>
  </>);
}
