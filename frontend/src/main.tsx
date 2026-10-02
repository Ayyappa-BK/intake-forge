import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
interface Result {
  batch: string;
  digest: string;
  accepted: number;
  rejected: number;
  quarantine: { line: number; reason: string; raw: string }[];
  distribution: Record<string, number>;
  reference: Record<string, number>;
  drift: number | null;
  warning: boolean;
  replayed: boolean;
}
interface Dashboard {
  batches: Result[];
  distribution: Record<string, number>;
  total: number;
  sample: string;
  shift: string;
}
type Api = { state: Dashboard; ingest: Result };
type Action = Exclude<keyof Api, "state">;
async function api<K extends keyof Api>(
  path: K,
  body?: Record<string, unknown>,
): Promise<Api[K]> {
  const response = await fetch(
    `/api/${path}`,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : undefined,
  );
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Request failed");
  return value;
}
function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}
function App() {
  const [state, setState] = useState<Partial<Dashboard>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api("state")
      .then(setState)
      .catch((e) => setError(e.message));
  }, []);
  async function run(path: Action, body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const data = await api(path, body);
      setResult(path === "ingest" ? (data as Result) : null);
      setState(await api("state"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  const [source, setSource] = useState<string | null>(null);
  const lines = source ?? state.sample ?? "";
  return (
    <>
      <header>
        <strong>Intake Forge</strong>
        <span>Dataset operations / quality gate</span>
      </header>
      <main>
        <div className="eyebrow">Ingest · quarantine · compare</div>
        <h1>Bad records belong outside the dataset.</h1>
        <p>
          A transactional JSONL intake gate with replay protection and
          label-distribution drift checks.
        </p>
        <div className="stats">
          <Stat value={state.total || 0} label="Accepted records in SQLite" />
          <Stat value={state.batches?.length || 0} label="Recent batches" />
          <Stat
            value={result?.rejected ?? "—"}
            label="Quarantined in last intake"
          />
        </div>
        <div className="grid">
          <section className="panel">
            <h2>Incoming batch</h2>
            <label htmlFor="records">One JSON record per line</label>
            <textarea
              id="records"
              value={lines}
              onChange={(e) => setSource(e.target.value)}
            />
            <div className="row">
              <button
                disabled={busy || !lines}
                onClick={() => void run("ingest", { lines })}
              >
                {busy ? "Validating…" : "Validate & commit"}
              </button>
              <button
                className="secondary"
                onClick={() => setSource(state.shift ?? "")}
              >
                Load shifted batch
              </button>
              <button className="secondary" onClick={() => setSource(null)}>
                Original sample
              </button>
            </div>
            <p>
              The exact same batch is safe to replay. A new batch is a new
              observation, even if record IDs recur.
            </p>
          </section>
          <section className="panel">
            <h2>Intake report</h2>
            {result ? (
              <>
                <p>
                  {result.accepted} accepted · {result.rejected} quarantined ·{" "}
                  {result.replayed
                    ? "replayed without writes"
                    : "committed atomically"}
                </p>
                <p>
                  Jensen–Shannon divergence:{" "}
                  <strong>
                    {result.drift === null
                      ? "No reference yet"
                      : result.drift.toFixed(3)}
                  </strong>{" "}
                  {result.warning && (
                    <span className="badge">Distribution shift</span>
                  )}
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Label</th>
                      <th>This batch</th>
                      <th>Prior dataset</th>
                    </tr>
                  </thead>
                  <tbody>
                    {["positive", "negative", "neutral"].map((label) => (
                      <tr key={label}>
                        <td>{label}</td>
                        <td>{result.distribution[label] || 0}</td>
                        <td>{result.reference[label] || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <h2 style={{ marginTop: 24 }}>Quarantine</h2>
                {result.quarantine.map((r) => (
                  <div key={r.line} className="passage">
                    <span className="badge">
                      Line {r.line} · {r.reason}
                    </span>
                    <pre>{r.raw}</pre>
                  </div>
                ))}
                {!result.rejected && (
                  <p>Every record passed the schema checks.</p>
                )}
              </>
            ) : (
              <p>
                Start with the sample, then ingest the shifted batch to see how
                the label mix changes.
              </p>
            )}
            <h2 style={{ marginTop: 24 }}>Recent batches</h2>
            {state.batches?.map((b) => (
              <p key={b.digest}>
                <code>{b.batch}</code> · {b.accepted} accepted · {b.rejected}{" "}
                rejected
              </p>
            ))}
          </section>
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <footer>
          Durable storage: .data/intake.sqlite3 · divergence threshold: 0.15
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
