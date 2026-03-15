import { useEffect, useState, useRef } from "react";

const API_BASE = "/api";

interface Booking {
  id: string;
  patient: string;
  time: string;
  provider: string;
  type: string;
  status: string;
}

interface LatencyLog {
  time: string;
  ms: number;
}

interface TranscriptLog {
  speaker: "SYS" | "PATIENT";
  text: string;
}

function App() {
  const [latencies, setLatencies] = useState<number[]>([]);
  const [latencyLogs, setLatencyLogs] = useState<LatencyLog[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);

  const [isCallActive, setIsCallActive] = useState(false);
  const [callSeconds, setCallSeconds] = useState(0);
  const [transcripts, setTranscripts] = useState<TranscriptLog[]>([
    { speaker: "SYS", text: "Awaiting audio stream..." },
  ]);

  const [phoneNumber, setPhoneNumber] = useState("+91");
  const [isCalling, setIsCalling] = useState(false);

  const handleCallAPI = async () => {
    if (!phoneNumber || phoneNumber.length < 8) return;
    setIsCalling(true);
    try {
      const res = await fetch(`${API_BASE}/call?to=${encodeURIComponent(phoneNumber)}`, {
        method: "POST"
      });
      const data = await res.json();
      console.log("Call response:", data);
      
      if (data.status === "calling") {
        // Prepare the UI for the incoming call
        setIsCallActive(true);
        setTranscripts([{ speaker: "SYS", text: `Calling ${phoneNumber}... Awaiting answer.` }]);
        setCallSeconds(0);
      } else {
        alert("Failed to call: " + data.detail);
      }
    } catch (err) {
      console.error(err);
      alert("Error initiating outbound call.");
    } finally {
      setIsCalling(false);
    }
  };

  const transcriptContainerRef = useRef<HTMLDivElement>(null);

  const mockTranscripts = [
    "Patient: I need to book an appointment next week.",
    "Agent: I can help with that. What day works best?",
    "Patient: Tuesday morning around 10 AM.",
    "Agent: Let me check Dr. Smith's availability.",
    "Agent: Tuesday at 10 AM is available. Booking now.",
  ];

  const transcriptIdxRef = useRef(0);

  // Auto-scroll transcripts
  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop =
        transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  // Fetch latency
  useEffect(() => {
    const fetchLatency = async () => {
      try {
        let latestLatency = 0;
        try {
          const res = await fetch(`${API_BASE}/latency`);
          if (res.ok) {
            const data = await res.json();
            latestLatency = data.latency_ms || data.latency || 0;
          }
        } catch (e) {
          // Mock
          if (isCallActive && Math.random() > 0.5) {
            latestLatency = Math.floor(Math.random() * (600 - 250) + 250);
          }
        }

        if (latestLatency > 0) {
          setLatencies((prev) => {
            const next = [...prev, latestLatency];
            if (next.length > 20) return next.slice(-20);
            return next;
          });

          setLatencyLogs((prev) => {
            const next = [
              ...prev,
              {
                time: new Date().toISOString().split("T")[1].slice(0, 12),
                ms: latestLatency,
              },
            ];
            if (next.length > 8) return next.slice(-8);
            return next;
          });

          if (isCallActive) {
            setTranscripts((prev) => [
              ...prev,
              {
                speaker: Math.random() > 0.5 ? "PATIENT" : "SYS",
                text: mockTranscripts[
                  transcriptIdxRef.current % mockTranscripts.length
                ],
              },
            ]);
            transcriptIdxRef.current++;
          }
        }
      } catch (e) {
        console.error(e);
      }
    };

    const interval = setInterval(fetchLatency, 1000);
    return () => clearInterval(interval);
  }, [isCallActive]);

  // Fetch bookings
  useEffect(() => {
    const fetchBookings = async () => {
      try {
        let newBookings: Booking[] = [];
        try {
          const res = await fetch(`${API_BASE}/bookings`);
          if (res.ok) {
            newBookings = await res.json();
          }
        } catch (e) {
          // Mock data
          newBookings = [
            {
              id: "BKG-9921",
              patient: "John Doe",
              time: new Date(Date.now() + 86400000).toLocaleString(),
              provider: "Dr. Smith",
              type: "Follow-up",
              status: "CONFIRMED",
            },
            {
              id: "BKG-9922",
              patient: "Jane Roe",
              time: new Date(Date.now() + 172800000).toLocaleString(),
              provider: "Dr. Adams",
              type: "Consultation",
              status: "CONFIRMED",
            },
            {
              id: "BKG-9920",
              patient: "Alice Tan",
              time: new Date(Date.now() + 3600000).toLocaleString(),
              provider: "Dr. Smith",
              type: "Urgent",
              status: "PENDING",
            },
          ];
        }
        setBookings(newBookings);
      } catch (e) {
        console.error(e);
      }
    };

    fetchBookings();
    const interval = setInterval(fetchBookings, 5000);
    return () => clearInterval(interval);
  }, []);

  // Call simulation toggle (removed the random active toggle so it only triggers when you click Call Me)
  useEffect(() => {
    let callTimerInterval: number | null = null;

    const toggleInterval = setInterval(() => {
      // Just auto-disconnect mock logic
      setIsCallActive((prev) => {
        if (prev && Math.random() > 0.95 && callSeconds > 30) {
          setTranscripts((t) => [
            ...t,
            { speaker: "SYS", text: "Call disconnected." },
          ]);
          setCallSeconds(0);
          return false;
        }
        return prev;
      });
    }, 5000);

    return () => {
      clearInterval(toggleInterval);
      if (callTimerInterval) clearInterval(callTimerInterval);
    };
  }, [callSeconds]);

  useEffect(() => {
    let interval: number;
    if (isCallActive) {
      interval = setInterval(() => {
        setCallSeconds((s) => s + 1);
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isCallActive]);

  const currentMs = latencies.length > 0 ? latencies[latencies.length - 1] : 0;
  const avgMs =
    latencies.length > 0
      ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
      : 0;
  const latencyPct = Math.min((currentMs / 1000) * 100, 100);

  const getLatencyColorClass = (ms: number) => {
    if (ms < 400)
      return {
        bar: "bg-primary shadow-[0_0_10px_#4cd7f6]",
        text: "text-primary drop-shadow-[0_0_8px_rgba(76,215,246,0.4)]",
        borderText: "border-primary text-primary/70",
      };
    if (ms < 800)
      return {
        bar: "bg-yellow-400 shadow-[0_0_10px_#fbbf24]",
        text: "text-yellow-400 drop-shadow-[0_0_8px_rgba(251,191,36,0.4)]",
        borderText: "border-yellow-400 text-yellow-400/70",
      };
    return {
      bar: "bg-tertiary shadow-[0_0_10px_#ffb2b7]",
      text: "text-tertiary drop-shadow-[0_0_8px_rgba(255,178,183,0.4)]",
      borderText: "border-tertiary text-tertiary/70",
    };
  };

  const currColor = getLatencyColorClass(currentMs);

  const formatTime = (secs: number) => {
    const m = String(Math.floor(secs / 60)).padStart(2, "0");
    const s = String(secs % 60).padStart(2, "0");
    return `${m}:${s}`;
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

      {/* HEADER / NAV */}
      <header className="flex justify-between items-center z-50">
        <div className="flex items-center gap-4 glass-panel neon-border-primary px-6 py-2 rounded-full">
          <span className="material-symbols-outlined text-primary">hub</span>
          <span className="font-headline font-bold tracking-widest text-lg hud-text text-primary">
            2CARE_AI_SYS
          </span>
        </div>
        
        {/* OUTBOUND CALL TRIGGER */}
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
        </div>

        <div>
          <a
            href="https://smith.langchain.com/"
            target="_blank"
            rel="noreferrer"
            className="glass-panel text-primary border border-primary/40 px-6 py-2 rounded-full flex items-center gap-2 hover:bg-primary/10 transition"
          >
            <span className="material-symbols-outlined text-sm">
              monitor_heart
            </span>
            <span className="text-xs uppercase tracking-widest font-bold">
              LangSmith Traces
            </span>
          </a>
        </div>
      </header>

      <main className="flex-1 grid grid-cols-12 grid-rows-6 gap-6 z-10">
        {/* LIVE CALL STATUS */}
        <section className="col-span-8 row-span-3 glass-panel neon-border-primary rounded-2xl p-6 flex flex-col justify-between relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(76,215,246,0.05),transparent)] pointer-events-none"></div>

          <div className="flex justify-between items-start z-10">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <div
                  className={`status-dot ${isCallActive ? "bg-tertiary shadow-[0_0_10px_#ffb2b7] animate-pulse" : "bg-white/20 shadow-none animate-none"}`}
                ></div>
                <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em]">
                  Live Call Status
                </h2>
              </div>
              {isCallActive ? (
                <h3 className="text-3xl font-headline font-light hud-text text-white">
                  Active Connection:{" "}
                  <span className="text-tertiary font-bold animate-pulse">
                    Patient Inbound
                  </span>
                </h3>
              ) : (
                <h3 className="text-3xl font-headline font-light hud-text text-white">
                  System Idle:{" "}
                  <span className="text-white/40">Awaiting Calls</span>
                </h3>
              )}
            </div>
            <div className="text-right">
              <div className="text-[10px] text-primary/50 uppercase tracking-widest mb-1">
                Duration
              </div>
              <div className="mono-data text-2xl text-primary drop-shadow-[0_0_8px_rgba(76,215,246,0.4)]">
                {formatTime(callSeconds)}
              </div>
            </div>
          </div>

          {/* WAVEFORM */}
          <div className="flex-1 flex items-center justify-center my-4 z-10">
            <div className="pulse-wave scale-150 opacity-80 transition-opacity">
              {Array.from({ length: 15 }).map((_, i) => {
                // Determine style dynamically for active state
                const isActiveClass = isCallActive
                  ? "animate-[pulse_1s_infinite]"
                  : "";
                const h = isCallActive ? Math.random() * 80 + 20 : 4;
                const isWhite = isCallActive && Math.random() > 0.7;
                return (
                  <div
                    key={i}
                    className={`pulse-bar transition-all duration-100 ease-in-out ${isActiveClass} ${isWhite ? "bg-white shadow-[0_0_15px_#fff]" : ""}`}
                    style={{
                      height: `${h}px`,
                      animationDuration: isCallActive
                        ? `${0.8 + Math.random()}s`
                        : "0s",
                    }}
                  />
                );
              })}
            </div>
          </div>

          {/* ACTIVE TRANSCRIPT */}
          <div
            ref={transcriptContainerRef}
            className="z-10 bg-black/40 border border-primary/20 rounded-lg p-3 h-24 overflow-y-auto w-full font-mono text-xs text-primary/80 space-y-2"
          >
            {transcripts.map((t, i) => {
              const isSys = t.speaker === "SYS";
              return (
                <div
                  key={i}
                  className={`flex gap-2 border-l-2 ${isSys ? "border-primary/40" : "border-white/40"} pl-2`}
                >
                  <span
                    className={`font-bold ${isSys ? "text-primary" : "text-white"}`}
                  >
                    {t.speaker}:
                  </span>
                  <span
                    className={`opacity-80 ${isSys ? "text-primary/90" : "text-white"}`}
                  >
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
            <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em]">
              Latency Telemetry
            </h2>
            <div className="text-[9px] mono-data bg-primary/20 text-primary px-2 py-0.5 rounded-sm border border-primary/40 font-bold">
              API /_LATENCY
            </div>
          </div>

          <div className="flex-1 flex flex-col justify-end gap-2 overflow-y-auto mb-4">
            {latencyLogs.map((log, i) => {
              const c = getLatencyColorClass(log.ms);
              return (
                <div
                  key={i}
                  className={`flex justify-between items-center text-xs mono-data border-l-2 pl-2 ${c.borderText}`}
                >
                  <span>{log.time}</span>
                  <span className="font-bold">{log.ms}ms</span>
                </div>
              );
            })}
          </div>

          <div className="mt-auto border-t border-primary/20 pt-4">
            <div className="flex justify-between items-end">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-primary/50 mb-1">
                  Avg Response Time
                </div>
                <div className="mono-data text-xl text-primary">{avgMs}ms</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-primary/50 mb-1 text-right">
                  Last Turn
                </div>
                <div
                  className={`mono-data text-2xl font-bold ${currColor.text}`}
                >
                  {currentMs}ms
                </div>
              </div>
            </div>
            <div className="w-full h-1 bg-primary/10 mt-2 rounded overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${currColor.bar}`}
                style={{ width: `${latencyPct}%` }}
              ></div>
            </div>
          </div>
        </section>

        {/* RECENT BOOKINGS */}
        <section className="col-span-12 row-span-3 glass-panel neon-border-primary rounded-2xl flex flex-col overflow-hidden">
          <div className="px-6 py-4 border-b border-primary/10 bg-black/20 flex justify-between items-center">
            <h2 className="text-xs font-black text-primary/70 uppercase tracking-[0.3em] flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px]">
                calendar_month
              </span>
              Recent Bookings
            </h2>
            <div className="px-2 py-1 bg-primary/10 border border-primary/30 rounded text-[9px] mono-data text-primary animate-pulse">
              LIVE SYNC
            </div>
          </div>

          <div className="flex-1 p-6 overflow-y-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-[10px] uppercase tracking-widest text-primary/50 border-b border-primary/20">
                  <th className="pb-3 font-medium">Patient / ID</th>
                  <th className="pb-3 font-medium">Time / Date</th>
                  <th className="pb-3 font-medium">Provider</th>
                  <th className="pb-3 font-medium">Type</th>
                  <th className="pb-3 font-medium text-right">Status</th>
                </tr>
              </thead>
              <tbody className="text-sm font-mono text-white/80">
                {bookings.map((b, i) => (
                  <tr
                    key={i}
                    className="border-b border-white/5 hover:bg-white/5 transition-colors group"
                  >
                    <td className="py-3">
                      <div className="font-bold text-white">{b.patient}</div>
                      <div className="text-[10px] text-primary/60">{b.id}</div>
                    </td>
                    <td className="py-3 text-white/80">{b.time}</td>
                    <td className="py-3 text-white/80">{b.provider}</td>
                    <td className="py-3">
                      <span className="px-2 py-1 rounded-sm bg-primary/10 border border-primary/20 text-[10px] text-primary">
                        {b.type}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <div
                        className={`flex items-center justify-end gap-2 text-[10px] uppercase font-bold ${b.status === "CONFIRMED" ? "text-primary" : "text-tertiary"}`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${b.status === "CONFIRMED" ? "bg-primary shadow-[0_0_5px_#4cd7f6]" : "bg-tertiary animate-pulse"}`}
                        ></span>
                        {b.status}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
