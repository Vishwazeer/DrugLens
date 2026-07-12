import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import {
  Activity, CheckCircle, Info, LayoutDashboard, Database,
  Shield, FileText, Settings, X, Cpu, Zap, Network,
  AlertTriangle, ArrowRightLeft, Loader2, FlaskConical,
  ChevronRight, Sparkles
} from 'lucide-react';

interface DemoCase {
  name: string;
  description: string;
  medication_text: string;
  patient_age: number;
  conditions: string[];
  expected_risk: string;
}

interface Interaction {
  drug1?: string; drug2?: string;
  drug_a?: string; drug_b?: string;
  description?: string; effect?: string;
  severity?: string;
}

interface BeersAlert {
  drug?: string; class_name?: string;
  matched_drugs?: string[];
  rationale?: string; recommendation?: string;
  severity?: string;
}

interface StoppRule {
  rule_description?: string;
  recommendation?: string;
  matched_drugs?: string[];
  severity?: string;
}

interface Alternative {
  drug: string;
  reason: string;
  safer_alternative: string;
  rationale: string;
  priority: 'high' | 'moderate';
}

interface Routing {
  route: 'edge' | 'cloud_llm';
  engine: string;
  model?: string;
}

/** An interaction predicted for a pair with NO curated-database entry. */
interface NovelPrediction {
  drug_a: string;
  drug_b: string;
  predicted_interaction: string;
  severity: string;
  confidence: string;
  mechanism?: string;
  recommendation?: string;
  smiles_used?: boolean;
}

interface NovelMeta {
  pairs_in_database: number;
  pairs_evaluated: number;
  model: string;
}

/** Live engine capabilities, read from the backend's loaded rulesets. */
interface EngineStats {
  ddi_pairs: number;
  beers_rules: number;
  stopp_rules: number;
  start_rules: number;
  stopp_start_total: number;
  conditions: number;
  median_engine_latency_ms: number;
}

interface AnalysisResult {
  risk_level: string;
  risk_score: number;
  patient_summary: string;
  parsed_medications: any[];
  beers_alerts: BeersAlert[];
  stopp_start: { stopp: StoppRule[]; start: StoppRule[] };
  interactions: Interaction[];
  predicted_interactions: any[];
  errors: string[];
  routing?: Routing;
}

// Dev: Vite serves the UI separately, so call the API on :8000.
// Production build: set VITE_API_URL="" so requests go to the same origin
// (FastAPI serves the built app itself). `??` keeps an intentional empty string.
const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export default function App() {
  const [demoCases, setDemoCases] = useState<DemoCase[]>([]);
  const [availableConditions, setAvailableConditions] = useState<string[]>([]);
  const [engineStats, setEngineStats] = useState<EngineStats | null>(null);

  // Patient Context State
  const [medicationText, setMedicationText] = useState('');
  const [patientAge, setPatientAge] = useState(75);
  const [patientEgfr, setPatientEgfr] = useState<number | ''>('');
  const [selectedConditions, setSelectedConditions] = useState<string[]>([]);

  // App State
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Streaming State
  const [streamedNarrative, setStreamedNarrative] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamRoute, setStreamRoute] = useState<'edge' | 'cloud_llm' | null>(null);
  const streamRef = useRef<EventSource | null>(null);

  // Alternatives State
  const [alternatives, setAlternatives] = useState<Alternative[]>([]);
  const [isFetchingAlts, setIsFetchingAlts] = useState(false);
  const [altsRequested, setAltsRequested] = useState(false);

  // Novel-DDI prediction state (pairs absent from the curated database)
  const [novelPredictions, setNovelPredictions] = useState<NovelPrediction[]>([]);
  const [novelMeta, setNovelMeta] = useState<NovelMeta | null>(null);
  const [isPredictingNovel, setIsPredictingNovel] = useState(false);
  const [novelRequested, setNovelRequested] = useState(false);

  // Modals & Settings
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [showSafetyModal, setShowSafetyModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [useGemma4, setUseGemma4] = useState(false);

  useEffect(() => {
    axios.get(`${API}/api/demo-cases`).then(res => setDemoCases(res.data));
    axios.get(`${API}/api/conditions`).then(res => setAvailableConditions(res.data));
    // Engine stats are read live from the backend's rulesets, never hardcoded,
    // so the numbers shown in the UI always match data/*.json.
    axios.get(`${API}/api/engine-stats`).then(res => setEngineStats(res.data)).catch(() => {});
  }, []);

  const resetState = () => {
    setMedicationText('');
    setPatientAge(75);
    setPatientEgfr('');
    setSelectedConditions([]);
    setResult(null);
    setError(null);
    setStreamedNarrative('');
    setStreamRoute(null);
    setAlternatives([]);
    setAltsRequested(false);
    setNovelPredictions([]);
    setNovelMeta(null);
    setNovelRequested(false);
    if (streamRef.current) { streamRef.current.close(); }
  };

  const loadDemoCase = (dc: DemoCase) => {
    setMedicationText(dc.medication_text);
    setPatientAge(dc.patient_age);
    setSelectedConditions(dc.conditions);
    setPatientEgfr('');
    setResult(null);
    setStreamedNarrative('');
    setStreamRoute(null);
    setAlternatives([]);
    setAltsRequested(false);
    setNovelPredictions([]);
    setNovelMeta(null);
    setNovelRequested(false);
  };

  const handleConditionToggle = (condition: string) => {
    setSelectedConditions(prev =>
      prev.includes(condition) ? prev.filter(c => c !== condition) : [...prev, condition]
    );
  };

  const buildPayload = () => ({
    medication_text: medicationText,
    patient_age: patientAge,
    patient_conditions: selectedConditions,
    patient_egfr: patientEgfr === '' ? null : Number(patientEgfr),
    use_gemma4: useGemma4,
  });

  const handleAnalyze = async () => {
    if (!medicationText.trim()) return;
    setIsAnalyzing(true);
    setError(null);
    setResult(null);
    setStreamedNarrative('');
    setStreamRoute(null);
    setAlternatives([]);
    setAltsRequested(false);
    setNovelPredictions([]);
    setNovelMeta(null);
    setNovelRequested(false);
    if (streamRef.current) { streamRef.current.close(); }

    try {
      const response = await axios.post(`${API}/api/analyze`, buildPayload());
      setResult(response.data);
      // After getting result, kick off streaming narrative
      startStreaming();
    } catch (err: any) {
      setError(err.message || 'Failed to analyze medications.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const startStreaming = () => {
    if (streamRef.current) { streamRef.current.close(); }
    setIsStreaming(true);
    setStreamedNarrative('');

    const payload = buildPayload();

    // Use fetch with streaming for SSE (EventSource doesn't support POST)
    fetch(`${API}/api/analyze/stream-narrative`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(async response => {
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) { setIsStreaming(false); return; }

      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'meta') {
                setStreamRoute(data.route);
              } else if (data.type === 'chunk') {
                setStreamedNarrative(prev => prev + data.text);
              } else if (data.type === 'done') {
                setIsStreaming(false);
              }
            } catch {}
          }
        }
      }
      setIsStreaming(false);
    }).catch(() => setIsStreaming(false));
  };

  const fetchNovel = async () => {
    if (!medicationText.trim()) return;
    setIsPredictingNovel(true);
    setNovelRequested(true);
    try {
      const response = await axios.post(`${API}/api/analyze/predict-novel`, buildPayload());
      setNovelPredictions(response.data.predictions || []);
      setNovelMeta({
        pairs_in_database: response.data.pairs_in_database,
        pairs_evaluated: response.data.pairs_evaluated,
        model: response.data.model,
      });
    } catch {
      setNovelPredictions([]);
    } finally {
      setIsPredictingNovel(false);
    }
  };

  const fetchAlternatives = async () => {
    if (!medicationText.trim()) return;
    setIsFetchingAlts(true);
    setAltsRequested(true);
    try {
      const response = await axios.post(`${API}/api/analyze/alternatives`, buildPayload());
      setAlternatives(response.data.alternatives || []);
    } catch {
      setAlternatives([]);
    } finally {
      setIsFetchingAlts(false);
    }
  };

  const getRiskGradient = (level: string) => {
    switch (level) {
      case 'HIGH': return 'from-red-500 to-rose-600';
      case 'MODERATE': return 'from-amber-400 to-orange-500';
      case 'LOW': return 'from-blue-400 to-cyan-500';
      case 'MINIMAL': return 'from-emerald-400 to-teal-500';
      default: return 'from-gray-400 to-gray-500';
    }
  };

  return (
    <div className="flex h-screen w-screen bg-gradient-to-br from-mint-bg via-[#e0f2f2] to-[#cce8e8] font-sans overflow-hidden print:h-auto print:w-auto print:overflow-visible print:bg-white">
      {/* Main Card — full-bleed: fills the viewport edge to edge */}
      <div className="w-full h-full bg-white flex overflow-hidden print:block print:h-auto print:w-auto print:overflow-visible">

        {/* Sidebar 1: Dark Teal Nav */}
        <div className="w-[90px] bg-gradient-to-b from-[#0c7a7d] via-teal-dark to-[#075558] flex flex-col items-center py-8 gap-8 flex-shrink-0 print:hidden">
          <div onClick={resetState} title="Reset" className="flex flex-col items-center gap-1.5 cursor-pointer group relative">
            <div className="absolute inset-[-6px] bg-white/10 rounded-2xl blur-md opacity-0 group-hover:opacity-100 transition-all duration-300" />
            <div className="p-3.5 bg-white rounded-2xl text-teal-dark shadow-lg transform group-hover:scale-110 group-hover:shadow-xl transition-all relative z-10">
              <LayoutDashboard className="w-5 h-5" />
            </div>
            <span className="text-[9px] text-white font-semibold tracking-wide uppercase">Home</span>
          </div>

          <div onClick={() => setShowStatsModal(true)} title="Engine Stats" className="flex flex-col items-center gap-1.5 cursor-pointer group relative">
            <div className="p-3.5 text-white/60 group-hover:text-white group-hover:bg-white/10 rounded-2xl transition-all">
              <Database className="w-5 h-5" />
            </div>
            <span className="text-[9px] text-white/60 group-hover:text-white font-medium tracking-wide uppercase transition-colors">Rules</span>
          </div>

          <div onClick={() => setShowSafetyModal(true)} title="Risk Methodology" className="flex flex-col items-center gap-1.5 cursor-pointer group relative">
            <div className="p-3.5 text-white/60 group-hover:text-white group-hover:bg-white/10 rounded-2xl transition-all">
              <Shield className="w-5 h-5" />
            </div>
            <span className="text-[9px] text-white/60 group-hover:text-white font-medium tracking-wide uppercase transition-colors">Safety</span>
          </div>

          <div onClick={() => window.print()} title="Export Report" className="flex flex-col items-center gap-1.5 cursor-pointer group relative">
            <div className="p-3.5 text-white/60 group-hover:text-white group-hover:bg-white/10 rounded-2xl transition-all">
              <FileText className="w-5 h-5" />
            </div>
            <span className="text-[9px] text-white/60 group-hover:text-white font-medium tracking-wide uppercase transition-colors">Export</span>
          </div>
        </div>

        {/* Sidebar 2: Patient Context */}
        <div className="w-[320px] bg-white border-r border-gray-100/80 flex flex-col overflow-y-auto custom-scrollbar flex-shrink-0 print:hidden">
          <div className="p-7">
            <div className="flex items-center gap-3 mb-7">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-teal-dark to-[#129A9E] flex items-center justify-center shadow-sm">
                <FlaskConical className="w-4 h-4 text-white" />
              </div>
              <h2 className="text-base font-bold text-gray-800 tracking-tight">Patient Context</h2>
            </div>

            <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.15em] mb-3">Demo Cases</h3>
            <div className="space-y-2.5 mb-8">
              {demoCases.map((dc, idx) => (
                <button
                  key={idx}
                  onClick={() => loadDemoCase(dc)}
                  className="w-full text-left p-3.5 rounded-2xl bg-gray-50/80 border border-gray-100 hover:border-teal-dark/30 hover:bg-gradient-to-r hover:from-[#EAF5F5] hover:to-[#f4fbfb] hover:shadow-[0_4px_15px_-3px_rgba(13,127,130,0.12)] hover:-translate-y-0.5 transition-all duration-200 group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#d2ecec] to-[#EAF5F5] flex items-center justify-center text-teal-dark font-bold text-sm border border-white/80 group-hover:from-teal-dark group-hover:to-[#129A9E] group-hover:text-white transition-all shadow-sm">
                      {idx + 1}
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-gray-800 text-xs leading-tight truncate">{dc.name}</div>
                      <div className="text-[10px] text-gray-400 mt-0.5 line-clamp-1">{dc.description.split('.')[0]}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.15em] mb-3">Patient Details</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1.5">Age (years)</label>
                <input
                  type="number"
                  value={patientAge}
                  onChange={e => setPatientAge(Number(e.target.value))}
                  className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-800 focus:border-teal-dark focus:ring-2 focus:ring-teal-dark/10 outline-none transition-all font-medium"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-1.5">eGFR <span className="font-normal text-gray-400">(mL/min/1.73m² · optional)</span></label>
                <input
                  type="number"
                  value={patientEgfr}
                  onChange={e => setPatientEgfr(e.target.value ? Number(e.target.value) : '')}
                  placeholder="e.g. 45"
                  className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-700 focus:border-teal-dark focus:ring-2 focus:ring-teal-dark/10 outline-none transition-all"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-gray-500 mb-2">Comorbidities</label>
                <div className="flex flex-wrap gap-1.5">
                  {availableConditions.map(cond => (
                    <button
                      key={cond}
                      onClick={() => handleConditionToggle(cond)}
                      className={`px-2.5 py-1 rounded-xl text-[10px] font-semibold transition-all duration-150 ${
                        selectedConditions.includes(cond)
                          ? 'bg-teal-dark text-white shadow-[0_2px_8px_rgba(13,127,130,0.35)] scale-105'
                          : 'bg-gray-100 text-gray-500 border border-gray-200 hover:bg-gray-200'
                      }`}
                    >
                      {cond}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 bg-[#F8FBFB] flex flex-col relative min-w-0 print:bg-white print:p-0 print:overflow-visible">

          {/* Header */}
          <div className="h-20 px-8 flex items-center justify-between border-b border-gray-100 bg-white/70 backdrop-blur-sm shrink-0 print:hidden">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-teal-dark to-[#129A9E] rounded-2xl flex items-center justify-center shadow-md">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-800 leading-tight">DrugLens Analysis Engine</h2>
                <p className="text-[10px] text-gray-400 font-medium tracking-wide">Polypharmacy Risk Intelligence</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Hardware Routing Indicator */}
              {streamRoute && (
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider border transition-all duration-500 ${
                  streamRoute === 'cloud_llm'
                    ? 'bg-blue-50 text-blue-700 border-blue-200 shadow-[0_0_12px_rgba(59,130,246,0.2)]'
                    : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${streamRoute === 'cloud_llm' ? 'bg-blue-500 animate-pulse' : 'bg-emerald-500'}`} />
                  {streamRoute === 'cloud_llm' ? 'Cloud LLM · Fireworks AI' : 'Edge Engine · Offline · 0 tokens'}
                </div>
              )}
              <button onClick={() => setShowSettingsModal(true)} className="w-9 h-9 rounded-xl bg-gray-100 text-gray-500 flex items-center justify-center hover:bg-gray-200 hover:text-gray-700 transition-all">
                <Settings className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Results Scrollable Area.
              pb must clear the floating input bar below (~240px) or the last
              card's controls (e.g. the Generate button) sit under it and become
              unclickable even at full scroll. */}
          <div className="flex-1 overflow-y-auto px-8 pt-7 pb-72 flex flex-col gap-6 custom-scrollbar print:overflow-visible print:p-0 print:pb-0">

            {!result && !isAnalyzing && (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-center pb-20">
                <div className="w-16 h-16 rounded-3xl bg-gradient-to-br from-[#EAF5F5] to-[#d2ecec] flex items-center justify-center">
                  <FlaskConical className="w-8 h-8 text-teal-dark opacity-70" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-500">No analysis yet</h3>
                  <p className="text-sm text-gray-400 mt-1">Load a demo case or paste a medication list below</p>
                </div>
              </div>
            )}

            {isAnalyzing && (
              <div className="flex items-center justify-center h-40 gap-3 text-teal-dark">
                <Loader2 className="w-6 h-6 animate-spin" />
                <span className="text-sm font-medium text-gray-500">Running deterministic analysis...</span>
              </div>
            )}

            {error && (
              <div className="p-5 rounded-2xl bg-red-50 border border-red-200 text-sm text-red-600 flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {error}
              </div>
            )}

            {result && (
              <div className="flex flex-col gap-5 animate-in fade-in slide-in-from-bottom-3 duration-500">

                {/* Print-only patient header */}
                <div className="print-header hidden print:block mb-6 pb-4 border-b-2 border-teal-800">
                  <div className="flex items-center justify-between">
                    <div>
                      <h1 className="text-2xl font-bold text-teal-800">DrugLens Clinical Safety Audit</h1>
                      <p className="text-[10px] text-gray-500 font-medium tracking-wide mt-0.5">Polypharmacy Risk Intelligence</p>
                    </div>
                    <div className="text-right">
                      <span className="text-[9px] font-bold uppercase text-gray-400 block">Overall Risk Status</span>
                      <span className="text-base font-extrabold text-red-600 uppercase">{result.risk_level} (Score: {result.risk_score})</span>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-4 mt-4 bg-gray-50 p-4 rounded-xl border border-gray-100">
                    <div>
                      <span className="text-[9px] font-bold uppercase text-gray-400 block">Patient Age</span>
                      <span className="text-xs font-semibold text-gray-800">{patientAge} years</span>
                    </div>
                    <div>
                      <span className="text-[9px] font-bold uppercase text-gray-400 block">Renal Function (eGFR)</span>
                      <span className="text-xs font-semibold text-gray-800">{patientEgfr || 'Not specified'} mL/min/1.73m²</span>
                    </div>
                    <div>
                      <span className="text-[9px] font-bold uppercase text-gray-400 block">Medications List</span>
                      <span className="text-xs font-semibold text-gray-800">{result.parsed_medications.length} items</span>
                    </div>
                  </div>
                  
                  {selectedConditions.length > 0 && (
                    <div className="mt-3 bg-gray-50/50 p-2.5 rounded-lg border border-gray-100/50">
                      <span className="text-[9px] font-bold uppercase text-gray-400 block">Comorbidities / Clinical Conditions</span>
                      <span className="text-xs text-gray-700 font-medium">{selectedConditions.join(', ')}</span>
                    </div>
                  )}

                  {/* Disclaimer — must travel with the exported clinical report */}
                  <div className="mt-3 p-2.5 rounded-lg border border-amber-200 bg-amber-50">
                    <span className="text-[9px] font-bold uppercase text-amber-700 block">Disclaimer</span>
                    <span className="text-[10px] text-amber-900 leading-snug">
                      Decision-support output for educational and research purposes only. Generated by an
                      automated rules engine (AGS Beers 2023, STOPP/START v3, curated DDI database) with
                      AI-generated narrative. Not a certified diagnostic device and not a substitute for
                      professional clinical judgement. Verify all findings before acting.
                    </span>
                  </div>
                </div>

                {/* Risk Banner */}
                <div className={`p-6 rounded-3xl bg-gradient-to-r ${getRiskGradient(result.risk_level)} text-white shadow-lg print:hidden`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-bold uppercase tracking-[0.2em] opacity-80 mb-1">Overall Risk Level</div>
                      <div className="text-4xl font-black tracking-tight">{result.risk_level}</div>
                      <div className="text-sm opacity-80 mt-1">{result.parsed_medications.length} medications · Score {result.risk_score}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] font-bold uppercase tracking-[0.15em] opacity-80 mb-1">Engine</div>
                      <div className="text-xs font-semibold opacity-90">
                        {result.routing?.engine || 'Deterministic'}
                      </div>
                      {result.routing?.model && (
                        <div className="text-[10px] opacity-70 mt-0.5">{result.routing.model}</div>
                      )}
                      <div className="flex items-center justify-end gap-1 mt-2">
                        <CheckCircle className="w-3.5 h-3.5 opacity-80" />
                        <span className="text-[10px] opacity-80">Deterministic · rule-based</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Streaming AI Narrative */}
                {(streamedNarrative || isStreaming) && (
                  <div className="p-5 rounded-2xl bg-white border border-blue-100 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-6 h-6 rounded-lg bg-blue-100 flex items-center justify-center">
                        <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                      </div>
                      <span className="text-[11px] font-bold text-blue-700 uppercase tracking-wider">
                        {isStreaming ? 'AI Clinical Narrative · Streaming...' : 'AI Clinical Narrative'}
                      </span>
                      {isStreaming && <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin ml-1" />}
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{streamedNarrative}</p>
                    {isStreaming && <span className="inline-block w-0.5 h-4 bg-blue-400 animate-pulse ml-0.5" />}
                  </div>
                )}

                {/* Interactions */}
                {result.interactions.length > 0 && (
                  <div className="p-5 rounded-2xl bg-white border border-amber-100 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-6 h-6 rounded-lg bg-amber-100 flex items-center justify-center">
                        <ArrowRightLeft className="w-3.5 h-3.5 text-amber-600" />
                      </div>
                      <span className="text-[11px] font-bold text-amber-700 uppercase tracking-wider">Drug-Drug Interactions</span>
                      <span className="ml-auto text-[10px] font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">{result.interactions.length}</span>
                    </div>
                    <div className="space-y-3">
                      {result.interactions.map((ix, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-amber-50/50 border border-amber-100">
                          <span className={`text-[9px] font-black px-2 py-1 rounded-lg mt-0.5 shrink-0 uppercase ${
                            ix.severity === 'major' || ix.severity === 'high'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-amber-100 text-amber-700'
                          }`}>{ix.severity || '?'}</span>
                          <div>
                            <div className="font-semibold text-gray-800 text-sm">
                              {ix.drug1 || ix.drug_a} ↔ {ix.drug2 || ix.drug_b}
                            </div>
                            <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{ix.description || ix.effect}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Beers Criteria */}
                {result.beers_alerts.length > 0 && (
                  <div className="p-5 rounded-2xl bg-white border border-red-100 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-6 h-6 rounded-lg bg-red-100 flex items-center justify-center">
                        <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
                      </div>
                      <span className="text-[11px] font-bold text-red-700 uppercase tracking-wider">Beers Criteria</span>
                      <span className="ml-auto text-[10px] font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{result.beers_alerts.length}</span>
                    </div>
                    <div className="space-y-3">
                      {result.beers_alerts.map((alert, i) => (
                        <div key={i} className="p-3 rounded-xl bg-red-50/50 border border-red-100">
                          <div className="font-semibold text-gray-800 text-sm">
                            {alert.matched_drugs?.join(', ') || alert.drug || alert.class_name}
                          </div>
                          <p className="text-xs text-gray-500 mt-1 leading-relaxed">{alert.rationale || alert.recommendation}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* STOPP / START */}
                {(result.stopp_start.stopp.length > 0 || result.stopp_start.start.length > 0) && (
                  <div className="p-5 rounded-2xl bg-white border border-teal-dark/10 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-6 h-6 rounded-lg bg-teal-dark/10 flex items-center justify-center">
                        <Shield className="w-3.5 h-3.5 text-teal-dark" />
                      </div>
                      <span className="text-[11px] font-bold text-teal-dark uppercase tracking-wider">STOPP / START Criteria</span>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      {result.stopp_start.stopp.length > 0 && (
                        <div>
                          <div className="text-[10px] font-bold text-red-600 uppercase tracking-wider mb-2">STOPP · Consider Stopping</div>
                          <div className="space-y-2">
                            {result.stopp_start.stopp.map((s, i) => (
                              <div key={i} className="flex items-start gap-2 text-xs text-gray-600 p-2 rounded-lg bg-red-50/60">
                                <span className="w-1.5 h-1.5 rounded-full bg-red-400 mt-1 shrink-0" />
                                {s.rule_description || s.recommendation}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {result.stopp_start.start.length > 0 && (
                        <div>
                          <div className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider mb-2">START · Consider Adding</div>
                          <div className="space-y-2">
                            {result.stopp_start.start.map((s, i) => (
                              <div key={i} className="flex items-start gap-2 text-xs text-gray-600 p-2 rounded-lg bg-emerald-50/60">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1 shrink-0" />
                                {s.rule_description || s.recommendation}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Novel-DDI prediction: pairs with NO entry in the curated database.
                    This is the "novel drug blindspot" a lookup table cannot cover. */}
                {result && result.parsed_medications.length >= 2 && (
                  <div className="p-5 rounded-2xl bg-white border border-indigo-100 shadow-sm print:hidden">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-6 h-6 rounded-lg bg-indigo-100 flex items-center justify-center">
                        <Network className="w-3.5 h-3.5 text-indigo-600" />
                      </div>
                      <span className="text-[11px] font-bold text-indigo-700 uppercase tracking-wider">Novel Interaction Prediction</span>
                      <span className="text-[9px] text-indigo-500 ml-1 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100">Not in any database</span>
                      {novelMeta && (
                        <span className="ml-auto text-[10px] font-bold bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">
                          {novelPredictions.length}
                        </span>
                      )}
                    </div>

                    {!novelRequested && (
                      <div className="flex items-center gap-3">
                        <p className="text-xs text-gray-500 leading-relaxed flex-1">
                          Lookup tables only know pairs someone already indexed. Evaluate this patient's
                          <strong> un-indexed</strong> drug pairs against their molecular structures (PubChem SMILES)
                          to surface interactions no database contains.
                        </p>
                        <button
                          onClick={fetchNovel}
                          className="shrink-0 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-600 text-white text-xs font-semibold rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all flex items-center gap-2"
                        >
                          <Network className="w-3.5 h-3.5" /> Predict
                        </button>
                      </div>
                    )}

                    {isPredictingNovel && (
                      <div className="flex items-center gap-2 text-xs text-gray-400 py-3">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Evaluating un-indexed pairs against molecular structures...
                      </div>
                    )}

                    {novelRequested && !isPredictingNovel && novelMeta && (
                      <p className="text-[10px] text-gray-400 mb-3">
                        {novelMeta.pairs_in_database} pair(s) matched the curated database ·{' '}
                        <strong className="text-indigo-600">{novelMeta.pairs_evaluated} un-indexed pair(s)</strong> sent for prediction ·
                        model: {novelMeta.model}
                      </p>
                    )}

                    {novelRequested && !isPredictingNovel && novelPredictions.length === 0 && (
                      <p className="text-xs text-gray-400">No additional interactions predicted for the un-indexed pairs.</p>
                    )}

                    <div className="space-y-2">
                      {novelPredictions.map((p, i) => (
                        <div key={i} className="p-3 rounded-xl bg-indigo-50/40 border border-indigo-100">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-[9px] font-black px-2 py-0.5 rounded-lg uppercase ${
                              p.severity === 'major' ? 'bg-red-100 text-red-700'
                              : p.severity === 'moderate' ? 'bg-amber-100 text-amber-700'
                              : 'bg-gray-100 text-gray-600'
                            }`}>{p.severity}</span>
                            <span className="text-xs font-bold text-gray-800">{p.drug_a} ↔ {p.drug_b}</span>
                            <span className="text-[9px] text-gray-400">confidence: {p.confidence}</span>
                            {p.smiles_used && (
                              <span className="text-[9px] text-indigo-500 bg-white px-1.5 py-0.5 rounded border border-indigo-100">SMILES-grounded</span>
                            )}
                          </div>
                          <p className="text-xs text-gray-600 leading-relaxed">{p.predicted_interaction}</p>
                          {p.mechanism && <p className="text-[10px] text-gray-400 mt-1"><strong>Mechanism:</strong> {p.mechanism}</p>}
                          {p.recommendation && <p className="text-[10px] text-indigo-600 mt-0.5">{p.recommendation}</p>}
                        </div>
                      ))}
                    </div>

                    {novelPredictions.length > 0 && (
                      <p className="text-[9px] text-gray-400 mt-3 italic">
                        AI-predicted, not database-confirmed. Treat as a prompt for pharmacist review, not a verified finding.
                      </p>
                    )}
                  </div>
                )}

                {/* Clinical Alternatives CTA + Table — interactive only, excluded from the PDF export */}
                {result && ['HIGH', 'MODERATE'].includes(result.risk_level) && (
                  <div className="p-5 rounded-2xl bg-white border border-purple-100 shadow-sm print:hidden">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-6 h-6 rounded-lg bg-purple-100 flex items-center justify-center">
                        <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                      </div>
                      <span className="text-[11px] font-bold text-purple-700 uppercase tracking-wider">AI Prescribing Alternatives</span>
                      <span className="text-[9px] text-purple-500 ml-1 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-100">Cloud LLM · Structured JSON</span>
                    </div>

                    {!altsRequested && (
                      <div className="flex items-center gap-3">
                        <p className="text-xs text-gray-500 leading-relaxed flex-1">
                          Generate evidence-based safer alternatives for each flagged medication, personalized to this patient's age and renal function.
                        </p>
                        <button
                          onClick={fetchAlternatives}
                          className="shrink-0 px-4 py-2 bg-gradient-to-r from-purple-500 to-violet-600 text-white text-xs font-semibold rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all flex items-center gap-2"
                        >
                          <Sparkles className="w-3.5 h-3.5" /> Generate
                        </button>
                      </div>
                    )}

                    {isFetchingAlts && (
                      <div className="flex items-center gap-2 text-purple-600 text-sm mt-2">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Generating alternatives via Fireworks AI...
                      </div>
                    )}

                    {altsRequested && !isFetchingAlts && alternatives.length === 0 && (
                      <p className="text-xs text-gray-400 mt-2">No alternatives generated. Ensure the Fireworks API key is active.</p>
                    )}

                    {alternatives.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {alternatives.map((alt, i) => (
                          <div key={i} className="p-3 rounded-xl bg-purple-50/60 border border-purple-100 grid grid-cols-[1fr_auto_1fr] gap-3 items-center">
                            <div>
                              <div className="text-xs font-bold text-gray-800">{alt.drug}</div>
                              <div className="text-[10px] text-red-600 mt-0.5">{alt.reason.slice(0, 60)}...</div>
                            </div>
                            <ChevronRight className="w-4 h-4 text-purple-400" />
                            <div>
                              <div className="text-xs font-bold text-emerald-700">{alt.safer_alternative}</div>
                              <div className="text-[10px] text-gray-500 mt-0.5">{alt.rationale}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

              </div>
            )}
          </div>

          {/* Input Area */}
          <div className="absolute bottom-0 left-0 right-0 p-6 pt-16 bg-gradient-to-t from-[#F8FBFB] via-[#F8FBFB]/95 to-transparent print:hidden">
            <div className="bg-white rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.07)] p-4 flex flex-col gap-3 border border-gray-100/80">
              <textarea
                value={medicationText}
                onChange={e => setMedicationText(e.target.value)}
                placeholder="Paste unstructured patient medication list here (e.g. 'warfarin 5mg once daily, digoxin 0.25mg once daily')..."
                className="w-full bg-transparent border-none focus:ring-0 resize-none h-16 text-sm text-gray-700 outline-none leading-relaxed placeholder:text-gray-300"
              />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[10px] text-gray-400 pl-1">
                  <Info className="w-3 h-3" />
                  <span>Offline deterministic engine · Fireworks AI escalation for complex cases</span>
                </div>
                <button
                  onClick={handleAnalyze}
                  disabled={isAnalyzing || !medicationText.trim()}
                  className="px-6 py-2.5 flex items-center gap-2 bg-gradient-to-r from-teal-dark to-[#129A9E] hover:from-[#0a6668] hover:to-teal-dark text-white rounded-xl transition-all duration-200 disabled:opacity-40 disabled:shadow-none shadow-[0_4px_15px_rgba(13,127,130,0.35)] hover:shadow-[0_6px_20px_rgba(13,127,130,0.45)] hover:-translate-y-0.5 text-sm font-semibold"
                >
                  {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                  {isAnalyzing ? 'Analyzing...' : 'Run Analysis'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Engine Stats Modal */}
      {showStatsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm" onClick={() => setShowStatsModal(false)}>
          <div className="bg-white rounded-[2rem] shadow-2xl p-8 max-w-md w-full border border-gray-100 relative" onClick={e => e.stopPropagation()}>
            <button className="absolute top-5 right-5 text-gray-300 hover:text-gray-600 transition-colors" onClick={() => setShowStatsModal(false)}><X className="w-5 h-5" /></button>
            <h3 className="text-xl font-bold text-gray-800 mb-1 flex items-center gap-2"><Cpu className="w-5 h-5 text-teal-dark" /> Engine Statistics</h3>
            <p className="text-xs text-gray-400 mb-6">Read live from the loaded rulesets — every number below is verifiable in <code>data/*.json</code></p>
            <div className="space-y-3">
              {[
                ['Drug-Drug Interaction Pairs', engineStats ? String(engineStats.ddi_pairs) : '…'],
                ['Beers Criteria Rules (2023)', engineStats ? String(engineStats.beers_rules) : '…'],
                ['STOPP/START Criteria v3', engineStats ? `${engineStats.stopp_rules} + ${engineStats.start_rules}` : '…'],
                ['Comorbidities Modelled', engineStats ? String(engineStats.conditions) : '…'],
                ['Deterministic Engine Latency (measured)', engineStats ? `${engineStats.median_engine_latency_ms} ms` : '…'],
                ['Routing Architecture', 'Edge + Cloud Hybrid (0 tokens on LOW/MINIMAL)'],
                ['Cloud LLM Backend', engineStats ? `Fireworks AI · ${result?.routing?.model ?? 'deepseek-v4-pro'}` : 'Fireworks AI'],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center p-3 bg-gray-50 rounded-2xl">
                  <span className="text-sm text-gray-500">{label}</span>
                  <span className="text-sm font-bold text-teal-dark">{value}</span>
                </div>
              ))}
            </div>
            <div className="mt-6 text-[10px] text-center text-gray-400 uppercase tracking-widest font-semibold flex items-center justify-center gap-1.5">
              <Network className="w-3 h-3" /> Token-Efficient Routing · LOW/MINIMAL = 0 tokens spent
            </div>
          </div>
        </div>
      )}

      {/* Safety Methodology Modal */}
      {showSafetyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm" onClick={() => setShowSafetyModal(false)}>
          <div className="bg-white rounded-[2rem] shadow-2xl p-8 max-w-md w-full border border-gray-100 relative" onClick={e => e.stopPropagation()}>
            <button className="absolute top-5 right-5 text-gray-300 hover:text-gray-600 transition-colors" onClick={() => setShowSafetyModal(false)}><X className="w-5 h-5" /></button>
            <h3 className="text-xl font-bold text-gray-800 mb-1 flex items-center gap-2"><Shield className="w-5 h-5 text-teal-dark" /> Risk Methodology</h3>
            <p className="text-sm text-gray-500 mb-5 leading-relaxed">DrugLens scores every regimen against 3 published clinical frameworks simultaneously — AGS Beers 2023, STOPP/START v3, and a curated DDI database — using fully transparent, auditable weights.</p>
            <div className="space-y-3 mb-5">
              {[
                { label: 'HIGH', color: 'red', desc: 'Score ≥ 12. Urgent clinical review required.', pts: 'Major DDI = 3 pts' },
                { label: 'MODERATE', color: 'amber', desc: 'Score 5–11. Close monitoring essential.', pts: 'Moderate DDI = 2 pts' },
                { label: 'LOW', color: 'blue', desc: 'Score 1–4. Routine pharmacist check.', pts: 'Beers / STOPP flag = 2 pts (high severity)' },
                { label: 'MINIMAL', color: 'emerald', desc: 'Score 0. No significant flags found.', pts: 'Beers / STOPP flag = 1 pt (moderate/low)' },
              ].map(({ label, color, desc, pts }) => (
                <div key={label} className={`flex items-center gap-3 p-3 rounded-xl bg-${color}-50 border border-${color}-100`}>
                  <div className={`w-20 h-7 rounded-full bg-${color}-100 text-${color}-700 text-[10px] font-black flex items-center justify-center border border-${color}-200`}>{label}</div>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-gray-700">{desc}</div>
                    <div className="text-[10px] text-gray-400">{pts}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="p-3 rounded-xl bg-gray-50 text-[10px] text-gray-500 leading-relaxed">
              MODERATE/HIGH cases escalate automatically to the Fireworks cloud model for a streaming clinical narrative. LOW/MINIMAL cases are answered entirely offline — zero LLM tokens spent.
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm" onClick={() => setShowSettingsModal(false)}>
          <div className="bg-white rounded-[2rem] shadow-2xl p-8 max-w-md w-full border border-gray-100 relative" onClick={e => e.stopPropagation()}>
            <button className="absolute top-5 right-5 text-gray-300 hover:text-gray-600 transition-colors" onClick={() => setShowSettingsModal(false)}><X className="w-5 h-5" /></button>
            <h3 className="text-xl font-bold text-gray-800 mb-6 flex items-center gap-2"><Settings className="w-5 h-5 text-teal-dark" /> Settings</h3>
            <div className="p-5 rounded-2xl border border-teal-dark/10 bg-gradient-to-br from-[#FAFCFC] to-[#F4F9F9] mb-4">
              <div className="flex justify-between items-start gap-4">
                <div className="flex-1">
                  <h4 className="font-bold text-teal-dark flex items-center gap-2 text-sm">Cloud AI Report Generation <Zap className="w-3.5 h-3.5 text-yellow-500 fill-current" /></h4>
                  <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                    Enables synchronous LLM report generation alongside the deterministic engine.
                    Note: The streaming narrative runs automatically regardless of this setting.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer flex-shrink-0 mt-1">
                  <input type="checkbox" className="sr-only peer" checked={useGemma4} onChange={() => setUseGemma4(!useGemma4)} />
                  <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-dark"></div>
                </label>
              </div>
            </div>
            <div className="text-[10px] text-gray-400 leading-relaxed px-1">
              Routing: LOW/MINIMAL risk cases use the offline deterministic engine only (0 tokens).
              MODERATE/HIGH cases automatically stream a cloud-model clinical narrative.
            </div>
          </div>
        </div>
      )}

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 5px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #cbd5e1; }
        @keyframes animate-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .animate-in { animation: animate-in 0.4s ease-out; }
      `}} />
    </div>
  );
}
