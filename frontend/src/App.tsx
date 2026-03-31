import React, { useEffect, useState, useRef } from "react";

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
    { speaker: "SYS", text: "Awaiting incoming connections..." },
  ]);
  const [latestSessionId, setLatestSessionId] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("+91");
  const [isCalling, setIsCalling] = useState(false);
  
  const [activeTab, setActiveTab] = useState("dashboard");

  const transcriptContainerRef = useRef<HTMLDivElement>(null);
  const callTimerRef = useRef<number | null>(null);

  const handleCallAPI = async () => {
    if (!phoneNumber || phoneNumber.length < 8) return;
    setIsCalling(true);
    try {
      const res = await fetch(`${API_BASE}/call?to=${encodeURIComponent(phoneNumber)}`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.status === "calling") {
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

  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop = transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/call-status`);
        if (!res.ok) return;
        const data = await res.json();
        const wasActive = isCallActive;
        setIsCallActive(data.is_active);
        if (data.latest_session_id) setLatestSessionId(data.latest_session_id);

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

  // ── Poll transcript ─────────────────────────
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

  // ── Poll latency ───────────────────────────────────────────────
  useEffect(() => {
    const fetchLatency = async () => {
      try {
        const res = await fetch(`${API_BASE}/latency?n=15`);
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

  const avgMs = latencyHistory.length > 0
    ? Math.round(latencyHistory.reduce((a, b) => a + b.total_ms, 0) / latencyHistory.length)
    : 0;
  
  const formatTime = (secs: number) => {
    const m = String(Math.floor(secs / 60)).padStart(2, "0");
    const s = String(secs % 60).padStart(2, "0");
    return `${m}:${s}`;
  };

  const statusColor = (status: string) => {
    if (status === "scheduled") return "bg-blue-100 text-blue-700 border-blue-200";
    if (status === "completed") return "bg-emerald-100 text-emerald-700 border-emerald-200";
    if (status === "cancelled") return "bg-red-100 text-red-700 border-red-200";
    return "bg-amber-100 text-amber-700 border-amber-200";
  };

  // ── Polling Langsmith Runs ────────────────────────────────────────────────
  const [langsmithRuns, setLangsmithRuns] = useState<any[]>([]);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  useEffect(() => {
    let interval: number;
    const fetchRuns = async () => {
      try {
        const res = await fetch(`${API_BASE}/langsmith/runs?limit=10`);
        if (res.ok) {
          const data = await res.json();
          if (data.runs) setLangsmithRuns(data.runs);
        }
      } catch (_) {}
    };

    if (activeTab === 'logs') {
      fetchRuns();
      interval = window.setInterval(fetchRuns, 5000);
    }
    return () => clearInterval(interval);
  }, [activeTab]);

  return (
    <div className="flex bg-slate-50 min-h-screen text-slate-800 font-sans">
      
      {/* ── SIDEBAR ── */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col items-center py-8 shadow-[4px_0_24px_rgba(0,0,0,0.02)] z-20">
        <div className="flex items-center gap-3 mb-12">
          <div className="w-10 h-10 rounded-xl clinical-gradient flex items-center justify-center shadow-lg shadow-blue-500/20">
            <span className="material-symbols-outlined text-white text-xl">vital_signs</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Medical<span className="text-blue-500">VoiceAgent</span></h1>
        </div>

        <nav className="w-full px-4 flex flex-col gap-2">
          <button 
            onClick={() => setActiveTab('dashboard')} 
            className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-all ${activeTab === 'dashboard' ? 'bg-blue-50 text-blue-600 shadow-sm' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'}`}
          >
            <span className="material-symbols-outlined text-[20px]">dashboard</span>
            Dashboard
          </button>
          <button 
            onClick={() => setActiveTab('logs')} 
            className={`flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-all ${activeTab === 'logs' ? 'bg-blue-50 text-blue-600 shadow-sm' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'}`}
          >
            <span className="material-symbols-outlined text-[20px]">call_log</span>
            Call Logs
          </button>
          <button 
            className="flex items-center gap-3 px-4 py-3 rounded-xl font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-900 transition-all opacity-50 cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[20px]">calendar_month</span>
            Calendar (Soon)
          </button>
        </nav>

        <div className="mt-auto px-6 w-full pb-4">
          <a
            href="https://smith.langchain.com/"
            target="_blank"
            rel="noreferrer"
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition-colors text-sm font-medium shadow-sm"
          >
            <span className="material-symbols-outlined text-sm">monitor_heart</span>
            LangSmith
          </a>
        </div>
      </aside>

      {/* ── MAIN CONTENT ── */}
      <main className="flex-1 flex flex-col max-h-screen overflow-y-auto">
        
        {/* HEADER */}
        <header className="flex justify-between items-center px-10 py-6 border-b border-slate-200/60 bg-white/50 backdrop-blur-md sticky top-0 z-10">
          <div>
            <h2 className="text-2xl font-bold text-slate-800">
              {activeTab === 'dashboard' ? 'Overview' : 'Call & Interaction Logs'}
            </h2>
            <p className="text-sm text-slate-500 mt-1">Monitor real-time voice sessions and patient appointments.</p>
          </div>

          {/* Quick Dialer */}
          <div className="flex items-center gap-3 bg-white p-1.5 rounded-full border border-slate-200 shadow-sm">
            <div className="flex items-center px-3 gap-2">
              <span className="material-symbols-outlined text-slate-400 text-[18px]">phone_enabled</span>
              <input
                type="text"
                placeholder="+1 (555) 000-0000"
                value={phoneNumber}
                onChange={e => setPhoneNumber(e.target.value)}
                className="bg-transparent outline-none text-slate-700 text-sm w-36 font-medium placeholder-slate-300 focus:ring-0"
              />
            </div>
            <button
              onClick={handleCallAPI}
              disabled={isCalling}
              className="bg-slate-900 hover:bg-blue-600 text-white px-5 py-2 rounded-full text-sm font-semibold transition-colors flex items-center gap-2"
            >
              {isCalling ? "Dialing..." : "Call Patient"}
            </button>
          </div>
        </header>

        <div className="p-10 flex flex-col gap-8 max-w-7xl mx-auto w-full">
          
          {/* KPI CARDS */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="glass-card p-6 flex flex-col justify-between">
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
                  <span className="material-symbols-outlined">record_voice_over</span>
                </div>
                <span className={`px-2.5 py-1 rounded-full text-[10px] uppercase font-bold tracking-wider ${isCallActive ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                  {isCallActive ? 'Live Audio' : 'Idle'}
                </span>
              </div>
              <div>
                <h3 className="text-slate-500 text-sm font-medium">System Status</h3>
                <div className="text-2xl font-bold text-slate-800 mt-1 flex items-center gap-2">
                  {isCallActive ? (
                    <>
                      <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-ring"></div>
                      Call in progress
                    </>
                  ) : 'Ready & Listening'}
                </div>
              </div>
            </div>

            <div className="glass-card p-6 flex flex-col justify-between">
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 rounded-full bg-teal-50 text-teal-600 flex items-center justify-center">
                  <span className="material-symbols-outlined">speed</span>
                </div>
              </div>
              <div>
                <h3 className="text-slate-500 text-sm font-medium">Average Latency</h3>
                <div className="text-2xl font-bold text-slate-800 mt-1">{avgMs} <span className="text-sm font-normal text-slate-400">ms</span></div>
              </div>
            </div>

            <div className="glass-card p-6 flex flex-col justify-between">
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <span className="material-symbols-outlined">calendar_today</span>
                </div>
              </div>
              <div>
                <h3 className="text-slate-500 text-sm font-medium">Appointments Booked</h3>
                <div className="text-2xl font-bold text-slate-800 mt-1">{bookings.length}</div>
              </div>
            </div>
          </div>

          {activeTab === 'dashboard' && (
            <div className="grid grid-cols-12 gap-8">
              
              {/* LIVE TRANSCRIPT */}
              <div className="col-span-12 lg:col-span-8 glass-card flex flex-col overflow-hidden">
                <div className="border-b border-slate-100 bg-slate-50/50 px-6 py-4 flex justify-between items-center">
                  <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                    <span className="material-symbols-outlined text-blue-500 text-[20px]">forum</span>
                    Live Communication
                  </h3>
                  <div className="text-sm font-mono text-slate-400">
                    Duration: {formatTime(callSeconds)}
                  </div>
                </div>
                
                <div 
                  ref={transcriptContainerRef}
                  className="flex-1 p-6 h-80 overflow-y-auto flex flex-col gap-4 bg-white/50"
                >
                  {transcripts.map((t, i) => {
                    const isSys = t.speaker === "SYS";
                    const isAgent = t.speaker === "AGENT";
                    return (
                      <div key={i} className={`flex ${isAgent ? 'justify-start' : isSys ? 'justify-center' : 'justify-end'}`}>
                        {isSys && (
                          <span className="bg-slate-100 text-slate-500 px-3 py-1 rounded-full text-xs font-mono">
                            {t.text}
                          </span>
                        )}
                        {!isSys && (
                          <div className={`max-w-[80%] rounded-2xl px-5 py-3 ${isAgent ? 'bg-blue-50 text-blue-900 rounded-tl-none border border-blue-100' : 'bg-slate-800 text-white rounded-tr-none shadow-md'}`}>
                            <p className="text-sm leading-relaxed">{t.text}</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* RECENT BOOKINGS (Sidebar widget) */}
              <div className="col-span-12 lg:col-span-4 glass-card flex flex-col overflow-hidden">
                <div className="border-b border-slate-100 bg-slate-50/50 px-6 py-4">
                  <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                    <span className="material-symbols-outlined text-teal-500 text-[20px]">event_available</span>
                    Recent Bookings
                  </h3>
                </div>
                <div className="flex-1 p-0 overflow-y-auto h-80">
                  {bookings.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-sm text-slate-400">
                      No appointments yet
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {bookings.slice(0, 5).map(b => (
                        <div key={b.id} className="p-4 hover:bg-slate-50/50 transition-colors">
                          <div className="flex justify-between items-start mb-1">
                            <span className="font-semibold text-sm text-slate-800">{b.patient_name ?? "Unknown Patient"}</span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${statusColor(b.status)}`}>
                              {b.status}
                            </span>
                          </div>
                          <div className="text-xs text-slate-500 mb-2">
                            Dr. {b.doctor_name ?? "—"} • {b.specialty ?? "General"}
                          </div>
                          <div className="text-xs text-slate-400 flex items-center gap-1 font-mono">
                            <span className="material-symbols-outlined text-[14px]">schedule</span>
                            {b.start_time ? new Date(b.start_time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="glass-card overflow-hidden">
              <div className="border-b border-slate-100 bg-slate-50/50 px-6 py-4 flex justify-between items-center">
                <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                  <span className="material-symbols-outlined text-indigo-500 text-[20px]">history</span>
                  Extracted Conversation History (from LangSmith)
                </h3>
                <span className="px-3 py-1 bg-green-100 text-green-700 text-xs font-bold rounded-full">LIVE SYNC</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                      <th className="px-6 py-4 font-medium">Trace Name / ID</th>
                      <th className="px-6 py-4 font-medium">Date & Time</th>
                      <th className="px-6 py-4 font-medium">Graph Latency</th>
                      <th className="px-6 py-4 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="text-sm divide-y divide-slate-100">
                    {langsmithRuns.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-6 py-12 text-center text-slate-400">Loading traces from LangSmith...</td>
                      </tr>
                    ) : (
                      langsmithRuns.map((run) => {
                        const isExpanded = expandedRunId === run.id;
                        return (
                          <React.Fragment key={run.id}>
                            <tr className={`transition-colors cursor-pointer ${isExpanded ? 'bg-blue-50/50' : 'hover:bg-slate-50/50'}`} onClick={() => setExpandedRunId(isExpanded ? null : run.id)}>
                              <td className="px-6 py-4">
                                <div className="font-semibold text-slate-800 mb-1">{run.name}</div>
                                <div className="font-mono text-xs text-slate-500">{run.id.slice(0, 8)}...</div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-slate-600">
                                {run.start_time ? new Date(run.start_time).toLocaleString() : '—'}
                              </td>
                              <td className="px-6 py-4">
                                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold ${run.latency_ms > 3000 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                                  <span className="material-symbols-outlined text-[14px]">timer</span>
                                  {run.latency_ms > 0 ? `${run.latency_ms.toFixed(0)} ms` : '—'}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-right">
                                <button className="text-blue-500 hover:bg-blue-50 p-2 rounded-full transition-colors inline-flex">
                                  <span className="material-symbols-outlined">
                                    {isExpanded ? 'expand_less' : 'expand_more'}
                                  </span>
                                </button>
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr>
                                <td colSpan={4} className="p-0 border-t-0">
                                  <div className="bg-slate-50/50 px-8 py-6 border-b border-slate-100">
                                    <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4 flex items-center gap-2">
                                      <span className="material-symbols-outlined text-[16px]">forum</span>
                                      Agent Interaction Log
                                    </h4>
                                    <div className="space-y-4 max-w-4xl bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
                                      {run.messages && run.messages.length > 0 ? (
                                        run.messages.map((msg: any, i: number) => (
                                          <div key={i} className={`flex ${msg.role === 'ai' ? 'justify-start' : 'justify-end'}`}>
                                            <div className={`max-w-[85%] rounded-2xl px-5 py-3 ${msg.role === 'ai' ? 'bg-blue-50 text-blue-900 rounded-tl-none border border-blue-100' : 'bg-slate-800 text-white rounded-tr-none shadow-md'}`}>
                                              <p className="text-sm leading-relaxed">{msg.text}</p>
                                            </div>
                                          </div>
                                        ))
                                      ) : (
                                        <div className="text-center text-slate-400 text-sm">No text messages recorded in this run.</div>
                                      )}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}

export default App;
