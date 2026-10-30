import React, { useEffect, useMemo, useRef, useState, useId } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import CapabilityGuide from './CapabilityGuide';
import QueryContext from './QueryContext';

const oid = x => typeof x === 'string' ? x : x?.$oid || String(x ?? '');
const names = { balanced_rrf: 'Balanced RRF', terminology_rrf: 'Terminology + RRF', context_rrf: 'Claim context + RRF' };
const domains = { Pricing: '#185d50', Plan: '#445ac7', Member: '#a56b19', Drug: '#8751a4', 'Prior auth': '#b75861' };
const money = cents => cents == null ? 'Unknown' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
const readable = value => JSON.stringify(value, null, 2);
const dateFor = id => id === 'oopm' ? '2026-10-25' : '2026-09-15';

async function readRunEvents(response, consume) {
  if(!response.ok){const data=await response.json();throw new Error(data.detail||'Pipeline request failed');}
  const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='';
  const line=value=>{if(value.trim())consume(JSON.parse(value));};
  while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();lines.forEach(line);}
  buffer+=decoder.decode();line(buffer);
}


function RuleGraph({ rows, onSelect, compact = false }) {
  const [hovered, setHovered] = useState(null);
  const [focused, setFocused] = useState(null);
  const active = hovered ?? focused;
  const markerId = `rule-arrow-${useId().replace(/:/g, "")}`;
  const nodes = new Map(), edges = [];
  rows.forEach(row => {
    (row.ruleGraph || [row]).forEach(n => {
      const key = oid(n.ruleId);
      const old = nodes.get(key);
      if (!old || (n.depth ?? 0) < (old.depth ?? 0)) nodes.set(key, n);
    });
  });
  const levels = new Map();
  [...nodes.values()].sort((a,b) => (a.depth || 0) - (b.depth || 0) || a.ruleName.localeCompare(b.ruleName)).forEach(n => {
    const level = Number(n.depth || 0);
    if (!levels.has(level)) levels.set(level, []);
    levels.get(level).push(n);
  });
  const positions = new Map();
  levels.forEach((items, level) => items.forEach((n, i) => positions.set(oid(n.ruleId), { x: 15 + level * 250, y: 18 + i * 88 })));
  nodes.forEach(n => (n.relationships || []).forEach(e => {
    if (positions.has(oid(e.targetRuleId))) edges.push({ from: oid(n.ruleId), to: oid(e.targetRuleId), type: e.relationship });
  }));
  const width = Math.max(compact ? 520 : 780, (Math.max(...levels.keys(), 0) + 1) * 250 + 15);
  const height = Math.max(210, Math.max(...[...levels.values()].map(x => x.length), 1) * 88 + 35);
  return <div className="rule-graph"><svg width={width} height={height} role="img" aria-label="Retrieved rule relationship graph">
    <defs><marker id={markerId} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>
    {edges.map((e,i) => { const a=positions.get(e.from), b=positions.get(e.to);return <g key={i} className={`graph-edge${active===e.from?" highlighted":""}`} data-source={e.from} data-target={e.to}><path d={`M${a.x+216},${a.y+31} C${a.x+245},${a.y+31} ${b.x-30},${b.y+31} ${b.x},${b.y+31}`} fill="none" stroke="#b5c7c0" strokeWidth="1.3" markerEnd={`url(#${markerId})`}/><title>{e.type}</title></g>; })}
    {[...nodes].map(([key,n]) => { const p=positions.get(key); return <g key={key} className={`graph-node${active===key?" active":""}${active&&edges.some(e=>e.from===active&&e.to===key)?" connected":""}`} onMouseEnter={()=>setHovered(key)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setFocused(key)} onBlur={()=>setFocused(null)} transform={`translate(${p.x},${p.y})`} role={compact?"group":"button"} tabIndex={0} aria-label={n.ruleName} onClick={compact?undefined:() => onSelect(n)} onKeyDown={compact?undefined:e => (e.key==='Enter'||e.key===' ') && onSelect(n)}><rect width="216" height="65" rx="8" fill="white" stroke={domains[n.ruleDomain] || '#667'} strokeOpacity=".6"/><text x="11" y="18" fontSize="9" fill={domains[n.ruleDomain] || '#667'}>{compact?n.ruleDomain:`${n.ruleDomain} · v${n.version} · depth ${Number(n.depth || 0)}`}</text><foreignObject x="11" y="25" width="194" height="36"><div xmlns="http://www.w3.org/1999/xhtml" className="graph-label">{n.ruleName}</div></foreignObject><title>{n.ruleName}</title></g>; })}
  </svg></div>;
}

function RelationshipHistory({ versions = [] }) {
  const [selection,setSelection]=useState(null);
  const [showChains,setShowChains]=useState(false);
  const selected=versions.find(v=>v.version===selection)||versions.at(-1);
  if(!selected)return <section className="relationship-history">Loading relationship versions…</section>;
  const nodes=(selected.nodes||[]).filter(n=>showChains||Number(n.depth||0)<=1);
  const end=String(selected.effEndDate).startsWith('9999')?'onward':`until ${String(selected.effEndDate).slice(0,10)} (exclusive)`;
  return <section className="relationship-history" aria-label="Versioned rule relationships">
    <header><div><span className="eyebrow">RELATIONSHIPS / MAC RULE</span><h3>Same rule. Different linked context.</h3></div><span className="relationship-count">{selected.directLinks} direct {selected.directLinks===1?'link':'links'}</span></header>
    <p>Select a version to see which rules it connects to. Rule calculations and individual document fields belong in section 01.</p>
    <div className="relationship-versions">{versions.map(v=><button key={v.version} aria-pressed={selected.version===v.version} onClick={()=>{setSelection(v.version);setShowChains(false);}}><strong>Version {v.version}</strong><small>From {String(v.effStartDate).slice(0,10)}</small><span>{v.directLinks===0?'No downstream links':`${v.directLinks} direct dependencies`}</span></button>)}</div>
    <div className="relationship-caption"><span>Effective {String(selected.effStartDate).slice(0,10)} · {end}</span>{selected.directLinks>0&&<button aria-expanded={showChains} onClick={()=>setShowChains(!showChains)}>{showChains?'Show direct links':'Show linked chains'}</button>}</div>
    <RuleGraph rows={[{ruleGraph:nodes}]} compact/>
    <div className="relationship-takeaway">{selected.directLinks===0?'This version has no declared downstream relationships.':showChains?`${selected.nodes.length} connected rule versions, including the MAC rule. Shared dependencies appear once; hover a link to see its type.`:'The MAC rule now requires list-version selection and product-identifier resolution. Follow the chains to see their supporting rules.'}</div>
  </section>;
}

function App() {
  const [catalog,setCatalog]=useState(null), [problem,setProblem]=useState('');
  const [chapter,setChapter]=useState('known'), [caseId,setCaseId]=useState('charge25');
  const [question,setQuestion]=useState('Why was I charged $25?');
  const [profile,setProfile]=useState('context_rrf'), [asOf,setAsOf]=useState('2026-10-15');
  const [depth,setDepth]=useState(5), [domain,setDomain]=useState('Pricing');
  const [vectorMode,setVectorMode]=useState('exact');
  const [fullRunning,setFullRunning]=useState(false), [fullRun,setFullRun]=useState(null);
  const fullAbort=useRef(null);
  const [rerank,setRerank]=useState(true), [plan,setPlan]=useState(null), [results,setResults]=useState({});
  const [selectedStage,setSelectedStage]=useState('match'), [selectedRule,setSelectedRule]=useState(null);
  const [tab,setTab]=useState('results'), [running,setRunning]=useState(false), [summary,setSummary]=useState('');
  const [dataView,setDataView]=useState('rule'), [copied,setCopied]=useState(false);
  const abort=useRef(null);
  const busy=running||fullRunning;
  useEffect(() => {
    const controller=new AbortController();
    fetch('/api/explorer/catalog',{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error('Atlas catalog unavailable. Check the backend connection.');setCatalog(await r.json());}).catch(e=>{if(e.name!=='AbortError')setProblem(e.message);});
    return()=>controller.abort();
  },[]);
  const requestBody=useMemo(()=>({chapter:chapter==='memory'?'discover':chapter,case_id:caseId,question,profile,domain,as_of:asOf,max_depth:Number(depth),rerank,execution_mode:'preview',vector_mode:vectorMode}),[chapter,caseId,question,profile,domain,asOf,depth,rerank,vectorMode]);
  useEffect(()=>{
    setResults({});setSummary('');setSelectedRule(null);setFullRun(null);
    if(chapter==='memory')return;
    setPlan(null);
    const controller=new AbortController();let active=true;
    const timer=setTimeout(()=>fetch('/api/explorer/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requestBody),signal:controller.signal}).then(async r=>{const d=await r.json();if(!r.ok)throw new Error(d.detail||'Unable to prepare pipeline');if(active){setPlan(d);setProblem('');setSelectedStage(old=>d.stages.some(s=>s.id===old)?old:d.stages[0].id);}}).catch(e=>{if(active&&e.name!=='AbortError')setProblem(e.message);}),200);
    return()=>{active=false;clearTimeout(timer);controller.abort();};
  },[requestBody,chapter]);
  const stage=plan?.stages.find(s=>s.id===selectedStage)||plan?.stages[0];
  const current=results[stage?.id];
  const entryDomains=[...new Set((catalog?.entryPoints||[]).map(r=>r.ruleDomain))].sort();
  function chooseChapter(value){setChapter(value);setTab('results');setSelectedStage(value==='known'?'match':'hybrid');}
  function chooseCase(value){setCaseId(value);const c=catalog.cases.find(c=>c.id===value);setQuestion(c.question);setAsOf(dateFor(value));setProfile(value==='oopm'?'terminology_rrf':'context_rrf');}
  async function run(e){
    e.preventDefault();setRunning(true);setProblem('');setResults({});setSummary('');setSelectedRule(null);setTab('results');
    abort.current=new AbortController();
    try{
      const response=await fetch('/api/explorer/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(requestBody),signal:abort.current.signal});
      await readRunEvents(response,event=>{if(event.kind==='plan')setPlan(event.plan);if(event.kind==='stage'){setSelectedStage(event.id);setResults(old=>({...old,[event.id]:event}));if(event.status==='failed')setProblem(event.message);}if(event.kind==='complete')setSummary(event.summary);});
    }catch(e){setProblem(e.name==='AbortError'?'Run cancelled. Completed read-only previews remain available.':e.message);}finally{setRunning(false);}
  }
  async function runFull(){
    setFullRunning(true);setFullRun({status:'running'});fullAbort.current=new AbortController();
    let finalStage=null,completed=false;
    try{
      const response=await fetch('/api/explorer/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...requestBody,execution_mode:'single'}),signal:fullAbort.current.signal});
      await readRunEvents(response,event=>{
        if(event.kind==='stage'&&event.status==='failed')throw new Error(event.message);
        if(event.kind==='stage'&&event.status==='completed')finalStage=event;
        if(event.kind==='complete'){
          if(!finalStage)throw new Error('Full pipeline returned no final results.');
          completed=true;setFullRun({status:'completed',elapsedMs:finalStage.elapsedMs,aggregationCalls:event.aggregationCalls,count:finalStage.count,graphNodes:finalStage.graphNodes});
        }
      });
      if(!completed)throw new Error('Full pipeline ended before completion.');
    }catch(error){setFullRun({status:'failed',message:error.name==='AbortError'?'Full run cancelled. Individual stage results are retained.':error.message});}
    finally{setFullRunning(false);}
  }
  const previewComplete=plan?.stages.every(stage=>results[stage.id]?.status==='completed');
  const previewMs=previewComplete?plan.stages.reduce((total,stage)=>total+results[stage.id].elapsedMs,0):null;
  const latencyDifference=previewMs!=null&&fullRun?.status==='completed'?previewMs-fullRun.elapsedMs:null;
  async function copy(){try{await navigator.clipboard.writeText(plan?.compass||'');setCopied(true);setTimeout(()=>setCopied(false),1600);}catch{setTab('pipeline');setProblem('Select and copy the pipeline text below.');}}
  const ruleDoc=selectedRule||current?.rows?.[0]||catalog?.sampleRule;
  const examples={rule:ruleDoc,versions:catalog?.versionExamples,raw:catalog?.rawExample,context:catalog?.contextExample};
  const versionExamples=catalog?.ruleVersionExamples||[];
  const isVersionExample=versionExamples.some(r=>oid(r._id)===oid(ruleDoc?._id));
  return <div className="studio">
    <nav className="topbar"><a href="/" className="brand"><span className="brand-icon">CKG</span><strong>Context Knowledge Graph</strong><span className="brand-divider"/>context engineering studio</a><div><span className="connection"><i className={catalog?'online':''}/>{catalog?'Atlas connected':'Connecting to Atlas'}</span><a href="/legacy" className="legacy-link">Agent explorer ↗</a></div></nav>
    <main>
      <header className="hero"><div><div className="eyebrow">MONGODB / RULE SELECTION</div><h1>From a question<br/>to the <em>right rules.</em></h1><p>Follow the evolution from a known starting point to relevance-driven retrieval.<br className="desktop"/> Inspect the documents, the pipeline, and the evidence at every step.</p></div><div className="inventory"><strong>{catalog?.totalRules?.toLocaleString()||'—'}</strong><span>versioned rule documents</span><small>{catalog?.curatedRules||'—'} curated strategy documents · 5 domains</small><div className="index-tags">{catalog?.indexes?.map(i=><span key={i.name} title={i.name}><i className={i.queryable?'online':''}/>{i.type==='vectorSearch'?'Voyage embeddings':'Lexical search'}</span>)}</div></div></header>
      <CapabilityGuide/>
      <div className="chapters" aria-label="Retrieval evolution">{[
        ['known','01','Domain entry points','$match → $graphLookup','Deterministic domain retrieval'],
        ['discover','02','Discover and traverse','Hybrid → $rerank → $graphLookup','Question-driven selection'],
        ['memory','03','Reuse what you know','Cache → procedure → retrieval','Coworker demo · conceptual'],
      ].map(([id,n,title,path,note])=><button key={id} disabled={busy} className={'chapter '+(chapter===id?'active':'')} onClick={()=>chooseChapter(id)} aria-pressed={chapter===id}><span className="chapter-number">{n}</span><strong>{title}</strong><code>{path}</code><small>{note}</small></button>)}</div>
      {problem&&<div className="alert" role="alert">{problem}</div>}
      {chapter==='memory'?<section className="memory-panel"><div className="eyebrow">THE NEXT EVOLUTION / HANDOFF</div><h2>Start with experience.<br/>Retrieve when the evidence needs it.</h2><p>This continuation belongs to the memory demo. These steps describe the integration contract; no cache or memory lookup runs on this screen.</p><div className="memory-flow">{catalog?.memoryHandoff?.steps.map((s,i)=><React.Fragment key={s}><div><small>0{i+1}</small><strong>{s}</strong></div>{i<4&&<span>→</span>}</React.Fragment>)}</div><div className="handoff-grid">{catalog?.memoryHandoff?.contract.map((c,i)=><article key={c}><span>0{i+1}</span><p>{c}</p></article>)}</div><button onClick={()=>chooseChapter('discover')}>Return to the live retrieval pipeline →</button></section>:<>
      <form className="controls" onSubmit={run}><div className="question-block"><label htmlFor="demo-question">Member question</label><textarea id="demo-question" value={question} maxLength={2000} required disabled={busy} onChange={e=>setQuestion(e.target.value)}/><div className="question-bottom"><select aria-label="Demo question" value={caseId} disabled={busy||!catalog} onChange={e=>chooseCase(e.target.value)}><option value="charge25">A $25 prescription charge</option><option value="oopm">Coinsurance after the OOP maximum</option></select><span>Selected claims provide evidence; wording supplies intent.</span></div></div><div className="settings">{chapter==='known'?<label>Rule domain<select aria-label="Rule domain" value={domain} disabled={busy} onChange={e=>setDomain(e.target.value)}>{entryDomains.map(d=><option key={d} value={d}>{d}</option>)}</select></label>:<label>Retrieval profile<select aria-label="Retrieval profile" value={profile} disabled={busy} onChange={e=>setProfile(e.target.value)}>{Object.entries(names).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>}<div className="setting-row"><label>Rules effective on<input aria-label="Rules effective on" type="date" value={asOf} required disabled={busy} onChange={e=>setAsOf(e.target.value)}/></label><label>maxDepth <strong>{depth}</strong><input aria-label="Maximum graph depth" type="range" min="0" max="7" value={depth} disabled={busy} onChange={e=>setDepth(e.target.value)}/></label></div>{chapter==='discover'&&<label className="checkbox"><input type="checkbox" checked={rerank} disabled={busy} onChange={e=>setRerank(e.target.checked)}/>Native Voyage reranking</label>}{chapter==='discover'&&<div className="execution-settings"><label>Vector search<select aria-label="Vector search mode" value={vectorMode} disabled={busy} onChange={e=>setVectorMode(e.target.value)}><option value="exact">Filtered exact — baseline</option><option value="ann">Filtered ANN — compare recall</option></select><small>50 results per branch{vectorMode==='ann'?' · numCandidates 1,000':''}</small></label></div>}<div className="run-row"><button className="primary" disabled={busy||!catalog||!plan} type="submit">{running?'Running pipeline…':'Run pipeline'} <span>↗</span></button>{running&&<button type="button" onClick={()=>abort.current?.abort()}>Cancel</button>}</div></div></form>
      <section className="workbench"><div className="workbench-head"><div><div className="eyebrow">LIVE AGGREGATION / context_knowledge_graph_demo.rulesSets</div><h2>Evidence, stage by stage.</h2></div><button className="copy" onClick={copy} disabled={!plan}>{copied?'Copied ✓':'Copy full Compass pipeline'}</button></div><div className="stage-rail">{plan?.stages.map((s,i)=>{const result=results[s.id];return <React.Fragment key={s.id}><button className={'stage-step '+(stage?.id===s.id?'selected ':'')+(result?.status||'')} onClick={()=>{setSelectedStage(s.id);setSelectedRule(null);}} aria-pressed={stage?.id===s.id}><span className="step-indicator">{result?.status==='completed'?'✓':String(i+1).padStart(2,'0')}</span><div><strong>{s.label}</strong><small>{result?.status==='running'?'Executing in Atlas…':result?.status==='completed'?`${result.count} document${result.count===1?'':'s'} · ${result.elapsedMs} ms${result.timingScope==='full-pipeline'?' total':''}`:result?.status==='included'?'Included · no separate preview':'Ready to inspect'}</small></div></button>{i<plan.stages.length-1&&<span className="rail-arrow">→</span>}</React.Fragment>;})}<div className="full-run-action"><button type="button" className="full-run-button" disabled={busy||!catalog||!plan} onClick={runFull}>{fullRunning?'Running full pipeline…':'Run full pipeline'} <span aria-hidden="true">↗</span></button>{fullRunning?<button type="button" className="cancel-full" onClick={()=>fullAbort.current?.abort()}>Cancel full run</button>:<small>{fullRun?.status==='completed'?`${fullRun.elapsedMs} ms · 1 aggregation`:'One aggregation · total latency'}</small>}</div></div>
      <section className="latency-comparison" aria-label="Pipeline latency comparison"><div><small>INDIVIDUAL STAGES · SUM OF PREVIEWS</small><strong>{previewMs==null?'—':`${previewMs} ms`}</strong><span>{previewComplete?`${plan.stages.length} aggregations · repeated upstream work`:'Run the individual stages to establish a comparison.'}</span></div><div><small>FULL PIPELINE · ONE AGGREGATION</small><strong>{fullRunning?'Running…':fullRun?.status==='completed'?`${fullRun.elapsedMs} ms`:'—'}</strong><span>{fullRun?.status==='completed'?`${fullRun.count} seeds · ${fullRun.graphNodes} connected versions`:'Use Run full pipeline at the end of the stage rail.'}</span></div><div><small>OBSERVED DIFFERENCE</small><strong>{latencyDifference==null?'—':latencyDifference===0?'Same time':`${Math.abs(latencyDifference)} ms ${latencyDifference>0?'less':'more'}`}</strong><span>One-run comparison; network and cache effects can change timings.</span></div>{fullRun?.status==='failed'&&<p className="full-run-error" role="alert">{fullRun.message}</p>}</section>
      <div className="stage-detail"><aside className="stage-explanation"><span className="pill">{current?.status==='completed'?'LIVE ATLAS RESULT':'PIPELINE STAGE'}</span><h3>{stage?.label||'Preparing pipeline…'}</h3><p>{stage?.why}</p><div className="io"><small>INPUT</small><p>{stage?.input}</p><small>OUTPUT</small><p>{stage?.output}</p></div>{stage?.note&&<details><summary>Design consideration</summary><p>{stage.note}</p></details>}<div className="selection-note"><strong>Evidence, then applicability.</strong><p>A retrieved rule is a candidate. Recorded claim facts, effective dates, conditions, and precedence establish what applies.</p></div></aside><div className="stage-content"><div className="content-tabs">{[['results','Retrieved rules'],['pipeline','Stage pipeline'],['graph','Relationships'],['context','Query context']].filter(([id])=>id!=='context'||chapter==='discover').map(([id,text])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{text}</button>)}</div>
      {tab==='results'&&<><div className="result-heading"><span>{current?.status==='completed'?`${current.count} seed document(s)${stage?.id==='graph'?` · ${current.graphNodes} unique connected versions`:''}`:current?.status==='included'?'Included in the single-pass pipeline; intermediate results were not separately retrieved.':'Run the pipeline to inspect actual results.'}</span>{current?.status==='running'&&<span className="working">Query running</span>}</div>{current?.rows?.length===0?<div className="empty">No rule versions matched this stage. Check the selected domain, effective date, or query profile.</div>:current?.rows?<div className="result-list">{current.rows.map((r,i)=><button key={oid(r._id)} className={'result-row '+(oid(selectedRule?._id)===oid(r._id)?'picked':'')} onClick={()=>{setSelectedRule(r);setDataView('rule');}}><span className="rank">{String(i+1).padStart(2,'0')}</span><div><strong>{r.ruleName}</strong><small><span style={{color:domains[r.ruleDomain]}}>{r.ruleDomain}</span> · version {r.version} · {r.entryPoint?'designated entry point':'concept / dependency candidate'}</small><code>{oid(r.ruleId)}</code>{r.rerankScore!=null&&results.hybrid?.rows&&<small>Hybrid #{results.hybrid.rows.findIndex(old=>oid(old._id)===oid(r._id))+1 || "—"} → reranked #{i+1}</small>}</div><div className="result-score">{r.rerankScore!=null?<><strong>{r.rerankScore.toFixed(4)}</strong><small>rerank score</small></>:r.fusionScore!=null?<><strong>{r.fusionScore.toFixed(4)}</strong><small>RRF score</small></>:<><strong>{r.ruleGraph?.length??'—'}</strong><small>graph nodes</small></>}</div><span className="row-arrow">↗</span></button>)}</div>:<div className="empty"><span className="empty-symbol">⌘</span><h3>{current?.status==='included'?'Included in the full pipeline.':'Your query is ready.'}</h3><p>{current?.status==='included'?'Select $graphLookup for the final results, or use Teaching mode for independent intermediate previews.':'Run it to see the documents returned by each stage. The stage pipeline is available before execution.'}</p></div>}</>}
      {tab==='pipeline'&&<div className="code-pane"><p>Executable cumulative prefix for this stage. Paste into Compass Aggregations / Text mode.</p><pre>{stage?.compass}</pre></div>}
      {tab==='graph'&&(current?.rows?<><div className="result-heading">{stage?.id==='graph'?'Declared links among the retrieved rule versions':'Run and select $graphLookup to see the full dependency graph.'}</div><RuleGraph rows={current.rows} onSelect={r=>{setSelectedRule(r);setDataView('rule');}}/><div className="graph-legend">{Object.entries(domains).map(([d,c])=><span key={d}><i style={{background:c}}/>{d}</span>)}</div></>:<div className="empty">Run the pipeline, then inspect the graph stage.</div>)}
      {tab==='context'&&chapter==='discover'&&<QueryContext profile={profile} plan={plan} asOf={asOf} money={money}/>}
      </div></div><div className="execution-note">{summary||plan?.executionNote}</div></section></>}
      <section className="data-model"><div className="data-heading"><div><div className="eyebrow">THE DOCUMENT MODEL / INSPECT THE FOUNDATION</div><h2>Context that keeps its connections.</h2></div><span>Source facts + explicit relationships + versioned applicability</span></div><div className="data-layout"><div className="model-choices">{[['rule','01','Versioned rule content','Compare specialty fee caps across three dated versions. The business ruleId stays stable.'],['versions','02','Versioned rule relationships','See how the linked rules change between MAC versions 2 and 3.'],['raw','03','Operational source record','The recorded outcome and source rule remain the facts to explain.'],['context','04','Source-shaped shared context','Operational fields at the root, with attributed enrichment alongside them.']].map(([id,n,title,desc])=><button key={id} className={dataView===id?'active':''} aria-pressed={dataView===id} onClick={()=>{setDataView(id);if(id==='rule'&&versionExamples.length)setSelectedRule(versionExamples[0]);}}><small>{n}</small><div><strong>{title}</strong><p>{desc}</p></div><span>↗</span></button>)}</div><div className="document-view">{dataView==='versions'?<RelationshipHistory versions={catalog?.versionExamples}/>:<><div><span>{dataView==='versions'?'rulesSets · MAC history':dataView==='raw'?'claims':dataView==='context'?'claims_context':'rulesSets · selected rule'}</span>{dataView==='rule'&&versionExamples.length>0?<select aria-label="Example rule version" value={isVersionExample?oid(ruleDoc?._id):'graph'} onChange={e=>{const chosen=versionExamples.find(r=>oid(r._id)===e.target.value);if(chosen)setSelectedRule(chosen);}}>{!isVersionExample&&<option value="graph">Selected graph rule</option>}{versionExamples.map(r=><option key={oid(r._id)} value={oid(r._id)}>Version {r.version} · from {String(r.effStartDate).slice(0,10)}</option>)}</select>:<small>Source IDs, dates, and versions</small>}</div><pre>{readable(examples[dataView])||'Loading source documents…'}</pre></>}</div></div></section>
      <footer><span>Context Knowledge Graph · Synthetic pharmacy context demonstration</span><span>Read-only pipeline execution · Memory integration is a separate demo</span></footer>
    </main>
  </div>;
}
if(window.location.pathname==='/legacy') import('./legacy.jsx');
else createRoot(document.getElementById('root')).render(<App/>);
