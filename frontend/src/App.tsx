import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Home, Activity, Zap, ArrowRight } from 'lucide-react';
import { GoogleGenerativeAI } from '@google/generative-ai';
import axios from 'axios';

// Initialize Gemini
const API_KEY = 'AIzaSyBBkhP7-v-pw_L003gIw-UmiJm-SZoUiXw';
const genAI = new GoogleGenerativeAI(API_KEY);

const PERSONAS = [
  {
    id: 'real_estate',
    name: 'REAL ESTATE',
    prompt: 'You are a sophisticated, high-stakes property mogul. Speak with aggressive market dominance.',
    font: 'font-serif'
  },
  {
    id: 'khan',
    name: 'KHAN',
    prompt: 'You are Khan. Speak with absolute, cold, genetically engineered superiority.',
    font: 'font-black tracking-tighter'
  },
  {
    id: 'surgeon',
    name: 'SURGEON',
    prompt: 'You are a precise, clinical, zero-error medical assistant. Analyze medical data and provide clinical insights.',
    font: 'font-mono'
  }
];

export default function App() {
  const [scrollProgress, setScrollProgress] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);
  
  // Chat States
  const [activePersona, setActivePersona] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Record<string, { role: string, content: string }[]>>({
    real_estate: [],
    khan: [],
    surgeon: []
  });
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      if (wrapperRef.current) {
        const { scrollLeft, scrollWidth, clientWidth } = wrapperRef.current;
        const progress = scrollLeft / (scrollWidth - clientWidth);
        setScrollProgress(progress);
      }
    };
    
    const wrapper = wrapperRef.current;
    if (wrapper) {
      wrapper.addEventListener('scroll', handleScroll);
      return () => wrapper.removeEventListener('scroll', handleScroll);
    }
  }, []);

  const handleSend = async (personaId: string) => {
    if (!input.trim()) return;
    
    const userMsg = input;
    setInput('');
    setMessages(prev => ({
      ...prev,
      [personaId]: [...prev[personaId], { role: 'user', content: userMsg }]
    }));

    if (personaId === 'surgeon' && userMsg.toLowerCase().includes('analyze')) {
      // Use DrugLens FastAPI Backend
      setIsAnalyzing(true);
      try {
        const response = await axios.post('http://localhost:8000/api/analyze', {
          medication_text: userMsg
        });
        
        const data = response.data;
        const risk = data.risk_level;
        const report = data.patient_summary || "Analysis complete. Review detailed structured report.";
        
        setMessages(prev => ({
          ...prev,
          [personaId]: [...prev[personaId], { role: 'system', content: `[DRUGLENS ACTIVE] Risk Level: ${risk}\n\n${report}` }]
        }));
      } catch (error) {
        setMessages(prev => ({
          ...prev,
          [personaId]: [...prev[personaId], { role: 'system', content: `[SYSTEM ERROR] Failed to connect to DrugLens API.` }]
        }));
      } finally {
        setIsAnalyzing(false);
      }
    } else {
      // Use Gemini via API
      try {
        const persona = PERSONAS.find(p => p.id === personaId);
        const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });
        const result = await model.generateContent(`${persona?.prompt}\n\nUser: ${userMsg}`);
        const responseText = result.response.text();
        
        setMessages(prev => ({
          ...prev,
          [personaId]: [...prev[personaId], { role: 'system', content: responseText }]
        }));
      } catch (error) {
        setMessages(prev => ({
          ...prev,
          [personaId]: [...prev[personaId], { role: 'system', content: 'Connection terminated. Re-establishing link...' }]
        }));
      }
    }
  };

  return (
    <div className="grain-bg w-full h-screen text-black relative">
      <div className="fixed-overlay blob-1"></div>
      <div className="fixed-overlay blob-2"></div>
      
      {/* Background Title */}
      <div className="fixed inset-0 flex items-center justify-center pointer-events-none z-0">
        <h1 className="text-[12vw] font-black tracking-tighter opacity-10">UNREAL</h1>
      </div>

      {/* Header Grid */}
      <header className="fixed top-0 left-0 w-full p-8 grid grid-cols-8 gap-4 border-b border-black/10 z-50">
        <div className="col-span-1 flex items-center gap-2">
          <Activity className="w-5 h-5" />
        </div>
        <div className="col-span-3">
          <p className="text-[10px] tracking-[0.2em] uppercase opacity-50">Persona_Node // 01</p>
          <p className="font-black tracking-tighter">NODES_ACTIVE</p>
        </div>
        <div className="col-span-4 flex justify-end items-center gap-4">
          <Home className="w-5 h-5 opacity-50" />
          <Zap className="w-5 h-5 opacity-50" />
        </div>
      </header>

      {/* Main Snap Container */}
      <div ref={wrapperRef} className="snap-wrapper pt-24">
        {PERSONAS.map((persona, index) => (
          <section key={persona.id} className="section">
            <motion.div 
              initial={{ opacity: 0, y: 50 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="w-[80vw] h-[70vh] flex flex-col items-center justify-center relative cursor-pointer"
              onClick={() => setActivePersona(persona.id)}
            >
              <h2 className={`text-6xl md:text-[8vw] ${persona.font} hover:scale-105 transition-transform duration-500`}>
                {persona.name}
              </h2>
              {activePersona === persona.id && (
                <div className="absolute inset-0 bg-white/90 backdrop-blur-md flex flex-col pt-10" onClick={(e) => e.stopPropagation()}>
                  
                  {/* Chat History */}
                  <div className="flex-1 overflow-y-auto p-8 space-y-8 no-scrollbar pb-24">
                    {messages[persona.id].map((msg, idx) => (
                      <div key={idx} className="w-full">
                        <p className="text-[10px] tracking-[0.2em] opacity-50 mb-2 uppercase">
                          {msg.role === 'user' ? 'USER_INPUT' : `${persona.name}_RESPONSE`}
                        </p>
                        <p className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
                          {msg.content}
                        </p>
                      </div>
                    ))}
                    {isAnalyzing && (
                      <p className="font-mono text-sm animate-pulse">[ANALYZING DRUGLENS DATA...]</p>
                    )}
                  </div>
                  
                  {/* Minimalist Terminal Input */}
                  <div className="absolute bottom-0 w-full p-8 bg-white border-t border-black/10">
                     <div className="flex items-center gap-4 border-b border-black pb-2">
                        <span className="font-mono text-xs opacity-50 whitespace-nowrap">CMD_INPUT &gt;</span>
                        <input 
                          type="text" 
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSend(persona.id)}
                          className="w-full bg-transparent outline-none font-mono text-sm"
                          placeholder={persona.id === 'surgeon' ? "Type 'analyze <medications>' to run DrugLens..." : "Enter command..."}
                          autoFocus
                        />
                        <button onClick={() => handleSend(persona.id)} className="opacity-50 hover:opacity-100 transition-opacity">
                          <ArrowRight className="w-4 h-4" />
                        </button>
                     </div>
                     <div className="flex justify-between items-center mt-2">
                        <p className="text-[10px] tracking-[0.2em] opacity-50">STABLE // AI_LINK_ACTIVE</p>
                        <button onClick={() => setActivePersona(null)} className="text-[10px] tracking-[0.2em] opacity-50 hover:opacity-100">
                          CLOSE_NODE
                        </button>
                     </div>
                  </div>

                </div>
              )}
            </motion.div>
          </section>
        ))}
      </div>

      {/* Progress Bar */}
      <div className="fixed bottom-0 left-0 w-full h-1 bg-black/5 z-50">
        <div 
          className="h-full bg-black transition-all duration-300"
          style={{ width: `${scrollProgress * 100}%` }}
        />
      </div>
    </div>
  );
}
