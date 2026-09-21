import { useEffect, useState } from "react";
import { api } from "../api/client";
import { notifyStopsChanged } from "../events";
type S = { id: number; route_id: number; seq: number; name: string; weight_kg: number; volume_l: number };
type R = { id: number; name: string };

export default function StopsPage() {
  const [routes, setRoutes] = useState<R[]>([]);
  const [rid, setRid] = useState<number | "">("");
  const [rows, setRows] = useState<S[]>([]);
  const [seq, setSeq] = useState("1");
  const [name, setName] = useState("");
  const [weight, setWeight] = useState("1");
  const [volume, setVolume] = useState("1");
  const [seqEdit, setSeqEdit] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<R[]>("/routes").then(r => { setRoutes(r); if (r[0]) setRid(r[0].id); }); }, []);
  useEffect(() => {
    if (rid === "") return;
    setErr(""); setMsg("");
    api<S[]>(`/stops?route_id=${rid}`).then(r => { setRows(r); setSeq(String(r.length + 1)); });
  }, [rid]);

  async function refresh() {
    const r = await api<S[]>(`/stops?route_id=${rid}`);
    setRows(r);
    notifyStopsChanged();
    return r;
  }

  async function createStop() {
    if (rid === "") return;
    setBusy(true); setErr(""); setMsg("");
    try {
      await api("/stops", {
        method: "POST",
        body: JSON.stringify({
          route_id: rid,
          seq: Number(seq), name,
          weight_kg: Number(weight), volume_l: Number(volume),
        }),
      });
      const r = await refresh();
      setName(""); setSeq(String(r.length + 1));
      setMsg(`已新增：序号必须从 1 起连续，当前 ${r.length} 个站点为 1..${r.length}`);
    } catch (e) {
      setErr(`新增失败：${e instanceof Error ? e.message : String(e)}；已有站点保持不变`);
    } finally { setBusy(false); }
  }

  async function saveSeq(id: number) {
    setBusy(true); setErr(""); setMsg("");
    try {
      await api(`/stops/${id}`, { method: "PATCH", body: JSON.stringify({ seq: Number(seqEdit[id]) }) });
      await refresh();
      setSeqEdit(prev => { const n = { ...prev }; delete n[id]; return n; });
      setMsg("序号已更新");
    } catch (e) {
      setErr(`修改序号失败：${e instanceof Error ? e.message : String(e)}；已有站点保持不变`);
      // drop the rejected draft so the input snaps back to the real seq
      setSeqEdit(prev => { const n = { ...prev }; delete n[id]; return n; });
      await refresh();
    } finally { setBusy(false); }
  }

  async function move(id: number, direction: "up" | "down") {
    setBusy(true); setErr(""); setMsg("");
    try {
      await api(`/stops/${id}/move`, { method: "POST", body: JSON.stringify({ direction }) });
      await refresh();
    } catch (e) {
      setErr(`移动失败：${e instanceof Error ? e.message : String(e)}`);
      await refresh();
    } finally { setBusy(false); }
  }

  async function reseq() {
    if (rid === "") return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api<S[]>(`/routes/${rid}/stops/resequence`, { method: "POST" });
      setRows(r);
      setSeq(String(r.length + 1));
      notifyStopsChanged();
      setMsg(`已按当前顺序重排为 1..${r.length}`);
    } catch (e) {
      setErr(`重排失败：${e instanceof Error ? e.message : String(e)}`);
    } finally { setBusy(false); }
  }

  return (<>
    <h2>订户点</h2>
    <div className="toolbar">
      <select value={rid} onChange={e => setRid(Number(e.target.value))}>{routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
      <button type="button" onClick={reseq} disabled={busy || rows.length === 0}>按当前顺序重排 1..n</button>
    </div>

    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err" data-testid="stop-error">{err}</div>}

    <form className="toolbar stop-form" onSubmit={e => { e.preventDefault(); createStop(); }}>
      <input aria-label="序号" type="number" min={1} value={seq} onChange={e => setSeq(e.target.value)} style={{ width: 80 }} />
      <input aria-label="名称" placeholder="站点名称" value={name} onChange={e => setName(e.target.value)} required />
      <input aria-label="重量kg" type="number" step="0.1" value={weight} onChange={e => setWeight(e.target.value)} style={{ width: 100 }} />
      <input aria-label="体积L" type="number" step="0.1" value={volume} onChange={e => setVolume(e.target.value)} style={{ width: 100 }} />
      <button type="submit" disabled={busy}>新增站点</button>
    </form>

    <table className="table">
      <thead><tr><th>序号</th><th>名称</th><th>重量 kg</th><th>体积 L</th><th>调整</th></tr></thead>
      <tbody>
        {rows.map((s, i) => (
          <tr key={s.id}>
            <td className="mono">
              <input
                aria-label={`序号-${s.name}`}
                type="number" min={1}
                style={{ width: 70 }}
                value={seqEdit[s.id] ?? String(s.seq)}
                onChange={e => setSeqEdit({ ...seqEdit, [s.id]: e.target.value })}
              />
              <button type="button" className="link-btn" disabled={busy || Number(seqEdit[s.id] ?? s.seq) === s.seq}
                onClick={() => saveSeq(s.id)}>改序号</button>
            </td>
            <td>{s.name}</td>
            <td className="mono">{s.weight_kg}</td>
            <td className="mono">{s.volume_l}</td>
            <td>
              <button type="button" className="link-btn" disabled={busy || i === 0} onClick={() => move(s.id, "up")}>上移</button>
              <button type="button" className="link-btn" disabled={busy || i === rows.length - 1} onClick={() => move(s.id, "down")}>下移</button>
            </td>
          </tr>
        ))}
        {!rows.length && <tr><td colSpan={5}>该路线暂无站点</td></tr>}
      </tbody>
    </table>
    <p className="hint">约束：同一路线序号必须从 1 起连续且不重复；出现跳号或冲突会被拒绝。可用上移/下移调整顺序后重排。</p>
  </>);
}
