import React, { useState, useEffect, useMemo, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { ReactFlow, Background, Controls, MarkerType } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import ReactMarkdown from 'react-markdown';
import './legacy.css';

const roles = ['coordinator', 'claim', 'member', 'drug', 'plan', 'pa'];
const domains = ['claim', 'member', 'drug', 'plan', 'pa'];
const collections = { claim: 'claims_context', member: 'members_context', drug: 'drugs_context', plan: 'plans_context', pa: 'prior_authorizations_context', policy: 'rules_policies' };
const sourceNames = { claims: 'claim', members: 'member', drugs: 'drug', plans: 'plan', prior_authorizations: 'pa', source_decisions: 'claim', rules_policies: 'policy' };
const label = x => x === 'pa' ? 'PA' : x[0].toUpperCase() + x.slice(1);
const sample = 'Why is my copay $75 this time when I only paid $25 for the same medicine last time?';
const modes = ['all', 'context_read', 'context_write', 'context_reinforcement', 'context_relationship'];
const names = { all: 'All activity', context_read: 'Reads', context_write: 'Writes', context_reinforcement: 'Reinforcement', context_relationship: 'Relationships' };

function BusinessDiagram({ findings }) {
  const ref = useRef(null);
  const [error, setError] = useState('');
  const definition = useMemo(() => {
    let text = 'flowchart TD\nQ["Pricing question"] --> C["Claim evidence"]\n';
    findings.forEach((f, i) => {
      const d = f.details;
      const safe = value => String(value ?? 'Unknown').replace(/["<>\n]/g, ' ');
      text += `C --> P${i}["${safe(f.claim_id)}: $${((d.member_paid_cents || 0) / 100).toFixed(2)} recorded"]\n`;
      if (d.plan_ref) text += `P${i} --> R${i}["${safe(d.plan_ref)} / ${safe(d.classification || d.rule_id)}"]\n`;
      text += `${d.plan_ref ? 'R' : 'P'}${i} --> E${i}["Evidence: ${safe(f.status)}"]\n`;
      if (f.missing.length) text += `E${i} --> G${i}["Gaps: ${safe(f.missing.join(', '))}"]\n`;
    });
    return text;
  }, [findings]);
  useEffect(() => {
    let cancelled = false;
    import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
      return mermaid.render('business-' + crypto.randomUUID().replaceAll('-', ''), definition);
    }).then(({ svg }) => {
      if (!cancelled && ref.current) {
        ref.current.innerHTML = svg;
        const root = ref.current;
        const highlight = source => {
          root.querySelectorAll('.flowchart-link').forEach(edge => {
            const id = edge.getAttribute('data-id') || edge.id || '';
            edge.classList.toggle('relationship-highlight', source != null && id.startsWith(`L_${source}_`));
          });
        };
        root.querySelectorAll('g.node').forEach(node => {
          const source = node.id.match(/flowchart-(.+)-\d+$/)?.[1];
          node.setAttribute('tabindex', '0');
          node.addEventListener('mouseenter', () => highlight(source));
          node.addEventListener('mouseleave', () => highlight(null));
          node.addEventListener('focus', () => highlight(source));
          node.addEventListener('blur', () => highlight(null));
        });
      }
    }).catch(() => { if (!cancelled) setError('Business diagram unavailable; source findings remain available.'); });
    return () => { cancelled = true; };
  }, [definition]);
  return <div className="business"><p className="muted">Generated from structured findings after execution. This is an explanation view, not a replay of model reasoning.</p>{error}<div ref={ref}/><details><summary>Mermaid source</summary><pre>{definition}</pre></details></div>;
}

function App() {
  const [hoveredNode, setHoveredNode] = useState(null);
  const [focusedNode, setFocusedNode] = useState(null);
  const activeNode = hoveredNode ?? focusedNode;
  const [nodeMeasurements, setNodeMeasurements] = useState({});
  function preserveNodeMeasurements(changes) {
    const dimensions = changes.filter(change => change.type === 'dimensions' && change.dimensions);
    if (!dimensions.length) return;
    setNodeMeasurements(previous => {
      const next = { ...previous };
      let changed = false;
      for (const change of dimensions) {
        const old = previous[change.id];
        if (old?.width !== change.dimensions.width || old?.height !== change.dimensions.height) {
          next[change.id] = change.dimensions;
          changed = true;
        }
      }
      return changed ? next : previous;
    });
  }
  const [question, setQuestion] = useState(sample);
  const [config, setConfig] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState('P02');
  const [events, setEvents] = useState([]);
  const [answer, setAnswer] = useState('');
  const [evidence, setEvidence] = useState([]);
  const [findings, setFindings] = useState([]);
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState('');
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState('all');
  const [view, setView] = useState('live');
  const [session, setSession] = useState(() => crypto.randomUUID());
  const [connected, setConnected] = useState(false);
  const abort = useRef(null);
  async function connect() {
    try {
      const c = await fetch('/api/config');
      if (!c.ok) throw new Error('API access failed (' + c.status + '). Check that the backend is running.');
      setConfig(await c.json());
      const r = await fetch('/api/scenarios');
      if (!r.ok) throw new Error('Claims unavailable. Check Atlas connection and permissions.');
      setScenarios((await r.json()).scenarios); setConnected(true); setProblem('');
    } catch (e) { setProblem(e.message); }
  }
  useEffect(() => { connect(); return () => abort.current?.abort(); }, []);

  async function investigate(e) {
    e.preventDefault(); setRunning(true); setProblem(''); setEvents([]); setAnswer(''); setEvidence([]); setFindings([]); setSelected(null); setView('live');
    abort.current = new AbortController();
    try {
      const res = await fetch('/api/investigate/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, scenario_id: scenarioId, session_id: session }), signal: abort.current.signal });
      if (!res.ok) throw new Error('Investigation request failed (' + res.status + ').');
      const reader = res.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      const consume = line => {
        if (!line.trim()) return;
        const event = JSON.parse(line); setEvents(old => [...old, event]);
        if (event.kind === 'answer') { setAnswer(event.answer); setEvidence(event.evidence); setFindings(event.findings); }
        if (event.status === 'failed' && event.kind === 'run') setProblem(event.message);
      };
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n'); buffer = lines.pop(); lines.forEach(consume);
      }
      buffer += decoder.decode(); consume(buffer);
    } catch (e) { setProblem(e.name === 'AbortError' ? 'Investigation cancelled. Completed context updates are retained.' : e.message); }
    finally { setRunning(false); }
  }

  const graph = useMemo(() => {
    const positions = { coordinator: [400, 0], claim: [400, 105], member: [0, 220], drug: [260, 220], plan: [520, 220], pa: [780, 220] };
    const nodes = roles.map(role => {
      const latest = events.filter(e => e.kind === 'agent' && e.agent === role).at(-1);
      return { id: role, position: { x: positions[role][0], y: positions[role][1] }, data: { label: <><strong>{label(role)} Agent</strong><small>{latest?.status || 'waiting'}</small></> }, className: 'agent-node ' + (latest?.status || ''), initialWidth: 190, initialHeight: 80, style: { width: 190 } };
    });
    [...domains, 'policy'].forEach((domain, i) => {
      const latest = events.filter(e => e.domain === domain && e.kind.startsWith('context_')).at(-1);
      nodes.push({ id: 'ctx-' + domain, position: { x: (i % 3) * 350, y: 380 + Math.floor(i / 3) * 115 }, data: { label: <><strong>{collections[domain]}</strong><small>{latest ? names[latest.kind] + ' · ' + latest.status : 'Shared business context'}</small></> }, className: 'context-node ' + (latest?.kind || ''), initialWidth: 245, initialHeight: 80, style: { width: 245 } });
    });
    domains.forEach((domain, i) => nodes.push({ id: 'op-' + domain, position: { x: i * 215, y: 660 }, data: { label: <><strong>{domain === 'pa' ? 'prior_authorizations' : domain + 's'}</strong><small>Operational · read only</small></> }, className: 'source-node', initialWidth: 195, initialHeight: 80, style: { width: 195 } }));
    const edges = [ ['coordinator', 'claim'], ...['member', 'drug', 'plan', 'pa'].map(d => ['claim', d]) ].map(([source, target]) => ({ id: 'route-' + target, source, target, type: 'smoothstep', style: { stroke: '#c0ccd1' } }));
    const latestEdges = new Map();
    events.filter(e => mode === 'all' || e.kind === mode).forEach(e => {
      let source, target, text;
      if (e.kind === 'context_read') { source = 'ctx-' + e.domain; target = e.agent; text = 'reads'; }
      if (e.kind === 'context_write' || e.kind === 'context_reinforcement') { source = e.agent; target = 'ctx-' + e.domain; text = e.kind === 'context_write' ? 'writes' : e.status; }
      if (e.kind === 'operational_read' && mode === 'all') { source = 'op-' + e.domain; target = e.agent; text = 'verifies'; }
      if (e.kind === 'context_relationship') { source = 'ctx-' + e.source_domain; target = 'ctx-' + e.target_domain; text = 'supported by'; }
      if (!source || !target || source === target || !nodes.some(n => n.id === source) || !nodes.some(n => n.id === target)) return;
      const id = source + ':' + target + ':' + text;
      latestEdges.set(id, { id, source, target, label: text, type: 'smoothstep', animated: running && e.status === 'running', markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: e.kind === 'context_write' ? '#b06113' : e.kind === 'context_relationship' ? '#6a4cc4' : '#087e75', strokeWidth: 2 }, data: e });
    });
    return { nodes: nodes.map(node => ({ ...node, measured: nodeMeasurements[node.id] })), edges: [...edges, ...latestEdges.values()] };
  }, [events, mode, running, nodeMeasurements]);

  const matching = selected ? events.filter(e => selected.startsWith('ctx-') ? e.domain === selected.slice(4) || e.target_domain === selected.slice(4) : selected.startsWith('op-') ? e.kind === 'operational_read' && e.domain === selected.slice(3) : e.agent === selected) : [];
  const visibleEvents = events.filter(e => mode === 'all' || e.kind === mode);
  const counts = kind => events.filter(e => e.kind === kind && e.status !== 'running').length;
  return <div className="app">
    <header><div><span className="eyebrow">Context Knowledge Graph / Pharmacy Demo</span><h1>Context, connected.</h1><p>Follow the evidence behind a claim’s price.</p></div><div className="environment"><span className={connected ? 'dot good' : 'dot'}/>{connected ? 'Atlas connected' : 'API not connected'}<small>Custom LangGraph runtime · {config?.model || 'Grove'}</small></div></header>
    <section className="request"><form onSubmit={investigate}><label htmlFor="question">Ask a pricing question</label><textarea id="question" value={question} onChange={e => setQuestion(e.target.value)} required maxLength={4000}/><div className="actions"><select aria-label="Choose prescription scenario" value={scenarioId} disabled={running} onChange={e => { const next = scenarios.find(s => s.id === e.target.value); if (next) { setScenarioId(next.id); setQuestion(next.question); } }}><option value="" disabled>Choose a prescription scenario…</option>{scenarios.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}</select><button className="primary" disabled={running || !connected}>{running ? 'Investigating…' : 'Investigate claim →'}</button>{running && <button type="button" onClick={() => abort.current.abort()}>Cancel</button>}</div></form><div className="session"><div>Memory: <strong>{config?.memory === 'not_configured' ? 'Not configured' : config?.memory || 'Checking'}</strong></div><button type="button" onClick={() => setSession(crypto.randomUUID())} disabled={running}>New session</button><small>Session {session.slice(0, 8)} · Context writes {config?.writes ? 'enabled' : 'disabled'}</small></div></section>
    {problem && <div className="problem" role="alert">{problem}</div>}
    <div className="metrics">{modes.slice(1).map(kind => <button key={kind} aria-pressed={mode === kind} onClick={() => setMode(mode === kind ? 'all' : kind)}><strong>{counts(kind)}</strong><span>{names[kind]}</span></button>)}</div>
    <section className="workspace"><div className="canvas-panel"><div className="panel-heading"><div><h2>Evidence in motion</h2><small>Reads · writes · reinforcement · cross-domain relationships</small></div><div className="switch"><button aria-pressed={view === 'live'} onClick={() => setView('live')}>Live workflow</button><button disabled={!findings.length} aria-pressed={view === 'business'} onClick={() => setView('business')}>Business explanation</button></div></div>{view === 'live' ? <div className="canvas"><ReactFlow nodes={graph.nodes} edges={graph.edges.map(edge => activeNode===edge.source ? {...edge, style:{...edge.style,stroke:'#237a51',strokeWidth:4},markerEnd:edge.markerEnd?{...edge.markerEnd,color:'#237a51'}:undefined} : edge)} onNodeMouseEnter={(_,node)=>setHoveredNode(node.id)} onNodeMouseLeave={()=>setHoveredNode(null)} onFocusCapture={event=>setFocusedNode(event.target.closest('.react-flow__node')?.dataset.id??null)} onBlurCapture={()=>setFocusedNode(null)} onNodesChange={preserveNodeMeasurements} fitView minZoom={0.35} maxZoom={1.5} nodesDraggable={false} onNodeClick={(_, n) => setSelected(n.id)} onEdgeClick={(_, e) => e.data && setSelected('ctx-' + (e.data.domain || e.data.source_domain))}><Background gap={22} size={1}/><Controls showInteractive={false}/></ReactFlow></div> : <BusinessDiagram findings={findings}/>}<div className="legend"><span>Agents</span><span>Shared context</span><span>Operational sources</span><span className="muted">Select a node to inspect its evidence and changes.</span></div></div><aside className="inspector"><h2>{selected ? selected.replace('ctx-', '') : 'Evidence inspector'}</h2>{!selected ? <p className="muted">Select a domain or agent. Inspect source versions, field changes, and which other domains supported a finding.</p> : <><h3>Latest activity</h3>{matching.slice(-12).reverse().map(e => <details key={e.id}><summary>{e.agent} · {e.kind.replaceAll('_', ' ')} · {e.status}</summary><pre>{JSON.stringify(e, null, 2)}</pre></details>)}<h3>Source documents</h3>{evidence.filter(e => selected === 'ctx-' + e.domain || selected === 'op-' + e.domain || selected === e.domain || matching.some(event => event.evidence_id === e.id)).map(e => <details key={e.id}><summary>{e.id}<small>version {e.source_version ?? 'content hash'} · {e.content_hash.slice(0, 10)}</small></summary><pre>{JSON.stringify(e, null, 2)}</pre></details>)}</>}</aside></section>
    <section className="bottom"><div className="answer"><h2>Supported explanation</h2>{answer ? <ReactMarkdown>{answer}</ReactMarkdown> : <p className="muted">The answer will appear here with evidence status, source references, and unresolved questions.</p>}{findings.map(f => f.details.agent_interpretation && <details key={f.claim_id}><summary>Claim agent interpretation · {f.claim_id}</summary><p>{f.details.agent_interpretation.summary}</p></details>)}</div><div className="timeline"><h2>Execution timeline <small>{visibleEvents.length} events</small></h2><div className="timeline-list">{visibleEvents.length ? [...visibleEvents].reverse().map(e => <button key={e.id} onClick={() => setSelected(e.domain ? 'ctx-' + e.domain : e.agent)}><span className="event-seq">{String(e.sequence).padStart(2, '0')}</span><span><strong>{label(e.agent)}</strong> · {e.kind.replaceAll('_', ' ')}<small>{e.collection || e.stage || e.document_id || ''}</small></span><span className={'status ' + e.status}>{e.status}</span></button>) : <p className="muted">Real execution events will appear as the investigation runs.</p>}</div></div></section>
    <footer>Synthetic demonstration data only. Business context is shared under the demo access policy; operational records are read only. Reuse is not corroboration.</footer>
  </div>;
}
createRoot(document.getElementById('root')).render(<><a href="/" style={{display:'block',padding:'12px 38px'}}>← Pipeline workbench</a><App/></>);
