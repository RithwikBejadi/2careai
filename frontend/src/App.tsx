import { useEffect, useState, useRef } from "react";

// In production, set VITE_API_BASE=https://your-backend.onrender.com/api
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

interface Booking {
  id: number;
  patient_name?: string;
  patient_phone?: string;
  doctor_name?: string;
  specialty?: string;
  start_time?: string;
  status: string;
}

interface LatencyEntry {
  transcript?: string;
  stt_ms: number;
  llm_ms: number;
  tts_first_chunk_ms: number;
  total_ms: number;
  session_id?: string;
}

interface TranscriptTurn {
  speaker: string;
  text: string;
}

function App() {
  const [latencyHistory, setLatencyHistory] = useState<LatencyEntry[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [isCallActive, setIsCallActive] = useState(false);
  const [callSeconds, setCallSeconds] = useState(0);
  const [transcripts, setTranscripts] = useState<TranscriptTurn[]>([
    { speaker: "SYS", text: "Awaiting audio stream..." },
  ]);
  const [latestSessionId, setLatestSessionId] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("+91");
  const [isCalling, setIsCalling] = useState(false);
  const transcriptContainerRef = useRef<HTMLDivElement>(null);
  const callTimerRef = useRef<number | null>(null);

  // ── Call handler ─────────────────────────────────────────────────────────
  const handleCallAPI = async () => {
    if (!phoneNumber || phoneNumber.length < 8) return;
    setIsCalling(true);
    try {
      const res = await fetch(`${API_BASE}/call?to=${encodeURIComponent(phoneNumber)}`, { method: "POST" });
      const data = await res.json();
      if (data.status === "calling") {
        setIsCallActive(true);
        setCallSeconds(0);
        setLatestSessionId(data.call_sid ?? null);
        setTranscripts([{ speaker: "SYS", text: `Calling ${phoneNumber}… Awaiting answer.` }]);
      } else {
        alert("Failed to call: " + (data.detail ?? JSON.stringify(data)));
      }
    } catch (err) {
      console.error(err);
      alert("Error initiating outbound call.");
    } finally {
      setIsCalling(false);
    }
  };

  // ── Auto-scroll transcript ────────────────────────────────────────────────
  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop = transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  // ── Poll call-status (every 2s) ────────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/call-status`);
        if (!res.ok) return;
        const data = await res.json();
        const wasActive = isCallActive;
        setIsCallActive(data.is_active);
        if (data.latest_session_id) setLatestSessionId(data.latest_session_id);

        // Call just ended
        if (wasActive && !data.is_active) {
          setCallSeconds(0);
          setTranscripts(prev => [...prev, { speaker: "SYS", text: "Call disconnected." }]);
        }
      } catch (_) {}
    };

    const interval = setInterval(poll, 2000);
    poll();
    return () => clearInterval(interval);
  }, [isCallActive]);

  // ── Call timer ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (isCallActive) {
      callTimerRef.current = window.setInterval(() => setCallSeconds(s => s + 1), 1000);
    } else {
      if (callTimerRef.current) clearInterval(callTimerRef.current);
    }
    return () => { if (callTimerRef.current) clearInterval(callTimerRef.current); };
  }, [isCallActive]);

  // ── Poll transcript (every 1s during active call) ─────────────────────────
  useEffect(() => {
    const pollTranscript = async () => {
      try {
        const url = latestSessionId
          ? `${API_BASE}/transcript?session_id=${latestSessionId}`
          : `${API_BASE}/transcript`;
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        if (data.turns && data.turns.length > 0) {
          const formatted = data.turns.map((t: TranscriptTurn) => ({
            speaker: t.speaker === "patient" ? "PATIENT" : t.speaker === "agent" ? "AGENT" : "SYS",
            text: t.text,
          }));
          setTranscripts([
            { speaker: "SYS", text: `Call active — Session: ${data.session_id?.slice(0, 8) ?? "..."}` },
            ...formatted,
          ]);
        }
      } catch (_) {}
    };

    const interval = setInterval(pollTranscript, 1000);
    return () => clearInterval(interval);
  }, [latestSessionId, isCallActive]);

  // ── Poll latency (every 2s) ───────────────────────────────────────────────
  useEffect(() => {
    const fetchLatency = async () => {
      try {
        const res = await fetch(`${API_BASE}/latency?n=10`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.history && data.history.length > 0) {
          setLatencyHistory(data.history);
        }
      } catch (_) {}
    };

    const interval = setInterval(fetchLatency, 2000);
    fetchLatency();
    return () => clearInterval(interval);
  }, []);

  // ── Poll bookings (every 5s) ──────────────────────────────────────────────
  useEffect(() => {
    const fetchBookings = async () => {
      try {
        const res = await fetch(`${API_BASE}/bookings`);
        if (res.ok) {
          const data = await res.json();
          setBookings(data);
        }
      } catch (_) {}
    };

    fetchBookings();
    const interval = setInterval(fetchBookings, 5000);
    return () => clearInterval(interval);
  }, []);

  // ── Derived latency stats ─────────────────────────────────────────────────
  const latest = latencyHistory[0];
  const currentMs = latest?.total_ms ?? 0;
  const avgMs = latencyHistory.length > 0
    ? Math.round(latencyHistory.reduce((a, b) => a + b.total_ms, 0) / latencyHistory.length)
    : 0;
  const latencyPct = Math.min((currentMs / 1500) * 100, 100);

  const getColor = (ms: number) => {
    if (ms < 400) return { bar: "bg-primary shadow-[0_0_10px_#4cd7f6]", text: "text-primary", border: "border-primary text-primary/70" };
    if (ms < 800) return { bar: "bg-yellow-400 shadow-[0_0_10px_#fbbf24]", text: "text-yellow-400", border: "border-yellow-400 text-yellow-400/70" };
    return { bar: "bg-tertiary shadow-[0_0_10px_#ffb2b7]", text: "text-tertiary", border: "border-tertiary text-tertiary/70" };
  };
  const currColor = getColor(currentMs);

  const formatTime = (secs: number) => {
    const m = String(Math.floor(secs / 60)).padStart(2, "0");
    const s = String(secs % 60).padStart(2, "0");
    return `${m}:${s}`;
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = { scheduled: "SCHEDULED", cancelled: "CANCELLED", rescheduled: "RESCHEDULED", completed: "COMPLETED" };
    return map[status] ?? status.toUpperCase();
  };

  const statusColor = (status: string) => {
    if (status === "scheduled") return "text-primary";
    if (status === "completed") return "text-green-400";
    if (status === "cancelled") return "text-tertiary";
    return "text-yellow-400";
  };

  return (
    <div className="h-screen w-screen p-6 relative flex flex-col gap-6">
      {/* ORNAMENTS */}
      <div className="corner-ornament top-4 left-4 border-t-2 border-l-2 border-primary/40"></div>
      <div className="corner-ornament top-4 right-4 border-t-2 border-r-2 border-primary/40 text-right">
        <div className="text-[8px] mono-data pr-1 pt-1">SYS.ONLINE</div>
      </div>
      <div className="corner-ornament bottom-4 left-4 border-b-2 border-l-2 border-primary/40 flex items-end">
        <div className="text-[8px] mono-data pl-1 pb-1">2CARE_AI // CORE</div>
      </div>
      <div className="corner-ornament bottom-4 right-4 border-b-2 border-r-2 border-primary/40 flex justify-end items-end">
        <div className="w-6 h-6 border-2 border-primary/20 rounded-full animate-spin-slow border-t-primary/60 mb-1 mr-1"></div>
      </div>

      {/* HEADER */}
      <header className="flex justify-between items-center z-50">
        <div className="flex items-center gap-4 glass-panel neon-border-primary px-6 py-2 rounded-full">
          <span className="material-symbols-outlined text-primary">hub</span>
          <span className="font-headline font-bold tracking-widest text-lg hud-text text-primary">2CARE_AI_SYS</span>
        </div>

        {/* CALL TRIGGER */}
        <div className="flex items-center gap-3 glass-panel px-4 py-2 rounded-full border border-primary/30">
          <input
            type="text"
            placeholder="+91..."
            value={phoneNumber}
            onChange={e => setPhoneNumber(e.target.value)}
            className="bg-transparent outline-none text-primary font-mono text-sm w-36 placeholder-primary/40 focus:ring-0"
          />
          <button
            onClick={handleCallAPI}
            disabled={isCalling}
            className="bg-primary/20 hover:bg-primary/40 text-primary px-4 py-1.5 rounded-full text-xs font-bold transition flex items-center gap-2 outline-none border border-primary/50"
          >
            <span className="material-symbols-outlined text-sm">call</span>
            {isCalling ? "CALLING..." : "CALL ME"}
          </button>
          {isCallActive && (
            <div className="flex items-center gap-1 text-tertiary text-xs font-bold animate-pulse">
              <span className="w-2 h-2 rounded-full bg-tertiary shadow-[0_0_6px_#ffb2b7]"></span>
              LIVE
            </div>
          )}
        </div>

        <a
          href="https://smith.langchain.com/"
          target="_blank"
          rel="noreferrer"
          className="glass-panel text-primary border border-primary/40 px-6 py-2 rounded-full flex items-center gap-2 hover:bg-primary/10 transition"
        >
          <span className="material-symbols-outlined text-sm">monitor_heart</span>
          <span className="text-xs uppercase tracking-widest font-bold">LangSmith Traces</span>
        </a>
      </header>

      <main className="flex-1 grid grid-cols-12 grid-rows-6 gap-6 z-10">
        {/* LIVE CALL STATUS */}
        <section className="col-span-8 row-span-3 glass-panel neon-border-primary rounded-2xl p-6 flex flex-col justify-between relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(76,215,246,0.05),transparent)] pointer-events-none"></div>

          <div className="flex justify-between items-start z-10">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div className={`status-dot ${isCallActive ? "bg-tertiary shadow-[0_0_10px_#ffb2b7] animate-pulse" : "bg-white/20 shadow-none animate-none"}`}></div>
                <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em]">Live Call Status</h2>
              </div>
              {isCallActive ? (
                <h3 className="text-3xl font-headline font-light hud-text text-white">
                  Active Connection: <span className="text-tertiary font-bold animate-pulse">LIVE</span>
                </h3>
              ) : (
                <h3 className="text-3xl font-headline font-light hud-text text-white">
                  System Idle: <span className="text-white/40">Awaiting Calls</span>
                </h3>
              )}
            </div>
            <div className="text-right">
              <div className="text-[10px] text-primary/50 uppercase tracking-widest mb-1">Duration</div>
              <div className="mono-data text-2xl text-primary drop-shadow-[0_0_8px_rgba(76,215,246,0.4)]">
                {formatTime(callSeconds)}
              </div>
            </div>
          </div>

          {/* WAVEFORM */}
          <div className="flex-1 flex items-center justify-center my-4 z-10">
            <div className="pulse-wave scale-150 opacity-80">
              {Array.from({ length: 15 }).map((_, i) => (
                <div
                  key={i}
                  className={`pulse-bar transition-all duration-150 ease-in-out`}
                  style={{
                    height: isCallActive ? `${Math.random() * 80 + 20}px` : "4px",
                    animationDuration: isCallActive ? `${0.8 + Math.random()}s` : "0s",
                  }}
                />
              ))}
            </div>
          </div>

          {/* LIVE TRANSCRIPT */}
          <div
            ref={transcriptContainerRef}
            className="z-10 bg-black/40 border border-primary/20 rounded-lg p-3 h-28 overflow-y-auto w-full font-mono text-xs text-primary/80 space-y-2"
          >
            {transcripts.map((t, i) => {
              const isSys = t.speaker === "SYS";
              const isAgent = t.speaker === "AGENT";
              return (
                <div
                  key={i}
                  className={`flex gap-2 border-l-2 ${isSys ? "border-primary/40" : isAgent ? "border-green-400/60" : "border-white/40"} pl-2`}
                >
                  <span className={`font-bold ${isSys ? "text-primary" : isAgent ? "text-green-400" : "text-white"}`}>
                    {t.speaker}:
                  </span>
                  <span className={`opacity-80 ${isSys ? "text-primary/90" : isAgent ? "text-green-300" : "text-white"}`}>
                    {t.text}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* LATENCY MONITOR */}
        <section className="col-span-4 row-span-3 glass-panel neon-border-primary rounded-2xl p-6 flex flex-col relative">
          <div className="flex items-center justify-between mb-4 z-10">
            <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em]">Latency Telemetry</h2>
            <div className="text-[9px] mono-data bg-primary/20 text-primary px-2 py-0.5 rounded-sm border border-primary/40 font-bold">
              API /_LATENCY
            </div>
          </div>

          <div className="flex-1 flex flex-col justify-end gap-2 overflow-y-auto mb-4">
            {latencyHistory.length === 0 ? (
              <div className="text-primary/30 text-xs mono-data text-center">No call data yet</div>
            ) : (
              latencyHistory.map((entry, i) => {
                const c = getColor(entry.total_ms);
                return (
                  <div key={i} className={`flex flex-col border-l-2 pl-2 ${c.border} text-xs mono-data mb-1`}>
                    <div className="flex justify-between">
                      <span className="text-primary/50 truncate w-28">{entry.transcript?.slice(0, 20) ?? "—"}</span>
                      <span className={`font-bold ${c.text}`}>{entry.total_ms}ms</span>
                    </div>
                    <div className="flex gap-3 text-[9px] text-white/30 mt-0.5">
                      <span>STT:{entry.stt_ms}ms</span>
                      <span>LLM:{entry.llm_ms}ms</span>
                      <span>TTS:{entry.tts_first_chunk_ms}ms</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="mt-auto border-t border-primary/20 pt-4">
            <div className="flex justify-between items-end">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-primary/50 mb-1">Avg Response</div>
                <div className="mono-data text-xl text-primary">{avgMs}ms</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-primary/50 mb-1 text-right">Last Turn</div>
                <div className={`mono-data text-2xl font-bold ${currColor.text}`}>{currentMs}ms</div>
              </div>
            </div>
            <div className="w-full h-1 bg-primary/10 mt-2 rounded overflow-hidden">
              <div className={`h-full transition-all duration-300 ${currColor.bar}`} style={{ width: `${latencyPct}%` }}></div>
            </div>
          </div>
        </section>

        {/* RECENT BOOKINGS */}
        <section className="col-span-12 row-span-3 glass-panel neon-border-primary rounded-2xl flex flex-col overflow-hidden">
          <div className="px-6 py-4 border-b border-primary/10 bg-black/20 flex justify-between items-center">
            <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em] flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px]">calendar_month</span>
              Recent Bookings
            </h2>
            <div className="px-2 py-1 bg-primary/10 border border-primary/30 rounded text-[9px] mono-data text-primary animate-pulse">
              LIVE SYNC
            </div>
          </div>

          <div className="flex-1 p-6 overflow-y-auto">
            {bookings.length === 0 ? (
              <div className="text-primary/30 mono-data text-sm text-center mt-4">No appointments yet</div>
            ) : (
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] uppercase tracking-widest text-primary/50 border-b border-primary/20">
                    <th className="pb-3 font-medium">Patient</th>
                    <th className="pb-3 font-medium">Time / Date</th>
                    <th className="pb-3 font-medium">Doctor</th>
                    <th className="pb-3 font-medium">Specialty</th>
                    <th className="pb-3 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="text-sm font-mono text-white/80">
                  {bookings.map((b) => (
                    <tr key={b.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="py-3">
                        <div className="font-bold text-white">{b.patient_name ?? "Unknown"}</div>
                        <div className="text-[10px] text-primary/60">{b.patient_phone ?? ""}</div>
                      </td>
                      <td className="py-3 text-white/80">
                        {b.start_time ? new Date(b.start_time).toLocaleString() : "—"}
                      </td>
                      <td className="py-3 text-white/80">{b.doctor_name ?? "—"}</td>
                      <td className="py-3">
                        <span className="px-2 py-1 rounded-sm bg-primary/10 border border-primary/20 text-[10px] text-primary">
                          {b.specialty ?? "—"}
                        </span>
                      </td>
                      <td className="py-3 text-right">
                        <div className={`flex items-center justify-end gap-2 text-[10px] uppercase font-bold ${statusColor(b.status)}`}>
                          <span className={`w-1.5 h-1.5 rounded-full bg-current shadow-[0_0_5px_currentColor]`}></span>
                          {statusLabel(b.status)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
