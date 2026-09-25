// Execution timing belongs to a prompt, not whichever result is on screen.
// Server start/end timestamps share a clock; never subtract a browser timestamp
// from one of them. Local elapsed time is only a fallback when both events were
// actually observed. In particular, recovering history must not time the outage.
const stamp = (value) => typeof value === "number" && Number.isFinite(value) ? value : null;
const span = (start, end) => start !== null && end !== null && end >= start ? end - start : null;
const TERMINAL = new Set(["execution_success", "execution_error", "execution_interrupted"]);

export class ExecutionTiming {
  constructor() { this.runs = new Map(); }

  get(promptId) {
    if (promptId === null || promptId === undefined || promptId === "") return null;
    const id = String(promptId);
    let run = this.runs.get(id);
    if (!run) {
      run = { promptId: id, start: null, end: null, localStart: null, localEnd: null,
              terminal: null, history: false, results: new Set() };
      this.runs.set(id, run);
      // Finished objects keep their numbers themselves. Unrelated queues need
      // not accumulate in every stage for the lifetime of the browser tab.
      if (this.runs.size > 64) {
        for (const [key, old] of this.runs) {
          if (key !== id && old.terminal && (old.history || !old.results.size)) this.runs.delete(key);
          if (this.runs.size <= 64) break;
        }
      }
    }
    return run;
  }

  start(promptId, timestamp, now = Date.now()) {
    const run = this.get(promptId);
    if (!run || run.terminal) return;
    run.start ??= stamp(timestamp);
    run.localStart ??= now;
  }

  stop(promptId, type, timestamp, now = Date.now()) {
    const run = this.get(promptId);
    if (!run || !TERMINAL.has(type)) return;
    run.terminal ??= type;
    run.end ??= stamp(timestamp);
    run.localEnd ??= now;
    this.refresh(run, now);
  }

  fromHistory(promptId, entry) {
    const run = this.get(promptId);
    if (!run) return;
    run.history = true;
    for (const [type, data] of entry?.status?.messages ?? []) {
      if (type === "execution_start") run.start = stamp(data?.timestamp) ?? run.start;
      if (TERMINAL.has(type)) {
        run.terminal = type;
        run.end = stamp(data?.timestamp) ?? run.end;
      }
    }
    // Older servers kept a final status but not timestamped messages. It says
    // the clock stopped, not when: no recovery-time local endpoint is invented.
    run.terminal ??= entry?.status?.status_str === "success" ? "execution_success"
      : entry?.status?.status_str === "error" ? "execution_error" : "history";
    this.refresh(run);
  }

  read(run, now = Date.now()) {
    if (!run) return { totalMs: null, totalPending: false };
    const totalMs = run.terminal
      ? (span(run.start, run.end) ?? span(run.localStart, run.localEnd))
      : span(run.localStart, now);
    return { totalMs, totalPending: !run.terminal };
  }

  attach(promptId, result) {
    const run = this.get(promptId);
    if (run) run.results.add(result);
    Object.assign(result, this.read(run));
  }

  refresh(run, now = Date.now()) {
    const timing = this.read(run, now);
    for (const result of run.results) Object.assign(result, timing);
  }

  refreshAll(now = Date.now()) {
    for (const run of this.runs.values()) this.refresh(run, now);
  }

  pendingResults() {
    return [...this.runs.values()].filter((run) => !run.terminal && run.results.size);
  }
}
