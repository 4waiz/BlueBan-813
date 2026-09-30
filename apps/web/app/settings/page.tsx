"use client";
/**
 * SETTINGS - who is operating, what this workspace holds, and alert delivery.
 *
 * The hosted demo keeps every visitor's workspace in their own browser
 * (localStorage): reviews, labels, samples, models and the audit log. Export
 * downloads it as JSON; reset returns it to the pipeline seed.
 */
import React, { useEffect, useState } from "react";
import { BellRing, Download, HardDrive, RotateCcw, Server, UserRound, Webhook } from "lucide-react";
import { DATA_MODE, getEngine, getOperator, mutate, setOperator, useEngineQuery } from "@/lib/engine";
import { Modal, Panel, toast } from "@/components/ui";

const WORKSPACE_KEY = "blueban813.workspace.v1";
const PREFS_KEY = "blueban813.alertprefs.v1";

function readPrefs(): { notify: boolean; webhook: string } {
  try { return { notify: false, webhook: "", ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch { return { notify: false, webhook: "" }; }
}

export default function SettingsPage() {
  const [op, setOp] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [prefs, setPrefs] = useState({ notify: false, webhook: "" });
  const [perm, setPerm] = useState<string>("default");
  const labels = useEngineQuery((e) => e.labels()).data || [];
  const models = useEngineQuery((e) => e.models()).data || [];
  const audit = useEngineQuery((e) => e.audit(undefined, undefined, 100000)).data || [];
  const incidents = useEngineQuery((e) => e.listIncidents()).data || [];
  useEffect(() => { setOp(getOperator()); setPrefs(readPrefs()); if (typeof Notification !== "undefined") setPerm(Notification.permission); }, []);
  const savePrefs = (p: typeof prefs) => { setPrefs(p); try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch { /* blocked */ } };

  const exportWs = () => {
    let raw: string | null = null;
    try { raw = localStorage.getItem(WORKSPACE_KEY); } catch { /* blocked */ }
    if (!raw) { toast("Nothing to export yet: the workspace is still the untouched seed.", "info"); return; }
    const blob = new Blob([raw], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `blueban813-workspace-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const reset = async () => {
    const e = getEngine();
    if (!e.reset) { toast("Reset is only available in the hosted workspace.", "err"); return; }
    await mutate((x) => x.reset!());
    setConfirm(false);
    toast("Workspace reset to the pipeline seed.");
  };

  return (
    <div className="h-full overflow-y-auto p-3 short:p-2">
      <div className="mb-3">
        <div className="hud-kicker">Settings</div>
        <h1 className="font-display text-[22px] font-bold tracking-wide">Operator, workspace and alerts</h1>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Operator identity" right={<UserRound size={16} className="text-beam" />} bodyClass="space-y-2 p-3 text-[12.5px]">
          <p className="text-muted">Every review, sample, training request and promotion is written to the audit log under this name. Promotion refuses system names: a model reaches production only on a named human&apos;s approval.</p>
          <div className="flex gap-2">
            <input value={op} onChange={(e) => setOp(e.target.value)} placeholder="Your name" className="flex-1 rounded-md border border-line bg-deep px-3 py-1.5" />
            <button className="btn btn-primary" disabled={!op.trim()} onClick={() => { setOperator(op); toast(`Operator set: ${op.trim()}`); }}>Save</button>
          </div>
        </Panel>

        <Panel title="Workspace" right={DATA_MODE === "live" ? <Server size={16} className="text-cyan" /> : <HardDrive size={16} className="text-cyan" />} bodyClass="space-y-2 p-3 text-[12.5px]">
          <p className="text-muted">{DATA_MODE === "live"
            ? "Connected to the BLUEBAN API (FastAPI + SQLite). State is shared by everyone using this server."
            : "Hosted mode: this workspace lives in your browser only. Nothing you do here is sent to a server or seen by other visitors."}</p>
          <div className="grid grid-cols-4 gap-2 text-center">
            {[["Incidents", incidents.length], ["Labels", labels.length], ["Models", models.length], ["Audit events", audit.length]].map(([k, v]) => (
              <div key={String(k)} className="rounded-md border border-edge bg-deep/60 py-2"><div className="hud-value text-[18px] font-bold">{v}</div><div className="text-[10.5px] text-muted">{k}</div></div>))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn" onClick={exportWs}><Download size={14} /> Export workspace (JSON)</button>
            <button className="btn" onClick={() => setConfirm(true)} disabled={DATA_MODE === "live"}><RotateCcw size={14} /> Reset to pipeline seed</button>
          </div>
        </Panel>

        <Panel title="Alert delivery" right={<BellRing size={16} className="text-caution" />} bodyClass="space-y-3 p-3 text-[12.5px]">
          <p className="text-muted">Alerts are written the way an operator needs them: where, how unusual for the season, what evidence exists, what is required. Never &quot;toxic algae&quot;.</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={prefs.notify} className="accent-[#2F7BFF]"
              onChange={async (e) => {
                const on = e.target.checked;
                if (on && typeof Notification !== "undefined" && Notification.permission !== "granted") {
                  const p = await Notification.requestPermission(); setPerm(p);
                  if (p !== "granted") { toast("Browser notifications were not allowed.", "err"); return; }
                }
                savePrefs({ ...prefs, notify: on });
              }} />
            Browser notification for new alerts <span className="text-dim">(permission: {perm})</span>
          </label>
          <div>
            <div className="mb-1 flex items-center gap-2"><Webhook size={14} className="text-muted" /> Webhook URL <span className="text-dim">(self-hosted API only)</span></div>
            <input value={prefs.webhook} onChange={(e) => savePrefs({ ...prefs, webhook: e.target.value })} placeholder="https://hooks.example.org/blueban" className="w-full rounded-md border border-line bg-deep px-3 py-1.5" />
            <p className="mt-1 text-[11px] text-dim">The hosted demo stores this in your browser and never calls it. The FastAPI backend posts the alert JSON (incident id, AOI, seasonal percentile, evidence, required action) to the URL configured in its environment (BLUEBAN_ALERT_WEBHOOK), so email or chat delivery stays outside the product.</p>
          </div>
        </Panel>

        <Panel title="About this build" bodyClass="space-y-1 p-3 text-[12px] text-muted">
          <div className="kv"><span>Product</span><span className="text-ink">BLUEBAN 813 · closed-loop coastal incident intelligence</span></div>
          <div className="kv"><span>Data mode</span><span className="hud-value">{DATA_MODE}</span></div>
          <div className="kv"><span>Team</span><a className="text-cyan hover:underline" href="https://kanbanstudios.ae/team-kanban" target="_blank" rel="noopener noreferrer">Team Kanban</a></div>
          <div className="kv"><span>Source</span><a className="text-cyan hover:underline" href="https://github.com/4waiz/BlueBan-813" target="_blank" rel="noopener noreferrer">github.com/4waiz/BlueBan-813</a></div>
        </Panel>
      </div>

      <Modal open={confirm} onClose={() => setConfirm(false)} title="Reset workspace?" width={440}>
        <p className="text-[13px] text-muted">This discards every review, label, sample, trained model and audit event in this browser and reloads the pipeline seed. Export first if you want to keep them.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn" onClick={() => setConfirm(false)}>Cancel</button>
          <button className="btn btn-primary" onClick={reset}><RotateCcw size={14} /> Reset</button>
        </div>
      </Modal>
    </div>
  );
}
