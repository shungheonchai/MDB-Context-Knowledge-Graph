import React from 'react';

const profiles = [
  ['balanced_rrf', 'Balanced RRF', 'Uses the question as written for lexical and semantic retrieval. No added glossary terms or claim facts.'],
  ['terminology_rrf', 'Terminology + RRF', 'Adds approved equivalents to the query; boosts terminology in rule names and subtypes. Related concepts add lexical signals.'],
  ['context_rrf', 'Claim context + RRF', 'Adds recorded payment, classification, and plan context; boosts rule names and subtypes using nonzero payment components.'],
];

export default function QueryContext({ profile, plan, asOf, money }) {
  const config = plan?.queryConfig;
  return <div className="context-pane">
    <h3>How this profile steers retrieval</h3>
    <p>The question supplies intent. The selected profile adds specific retrieval signals before rules are ranked.</p>
    <table className="profile-comparison"><thead><tr><th>Retrieval profile</th><th>What changes</th></tr></thead><tbody>{profiles.map(([id,label,description]) => <tr key={id} className={profile===id?'selected-profile':''}><th scope="row">{label}{profile===id&&<small>Selected</small>}</th><td>{description}</td></tr>)}</tbody></table>
    <p className="fusion-note">All three profiles keep lexical/vector RRF weights at 1:1. Lexical boosts change the lexical ranking before fusion; they do not change the fusion weights or establish rule applicability.</p>
    {config ? <>
      <section className="query-input"><h4>Query sent to semantic search and lexical rule text</h4><pre>{config.retrievalText}</pre></section>
      {profile==='terminology_rrf'&&<section className="query-terms"><h4>Terminology added for this question</h4><p><strong>Equivalent terms:</strong> {config.equivalentExpansions?.join(' · ')||'No glossary equivalents matched.'}</p><p><strong>Related concepts:</strong> {config.relatedConcepts?.join(' · ')||'No related concepts matched.'}</p><p>Equivalents expand the semantic query too. Related concepts contribute lexical boosts; they are not treated as synonyms.</p></section>}
      {profile==='context_rrf'&&<section className="query-terms"><h4>Recorded context added to this query</h4><p>{config.claimContext||'No recorded claim context is available.'}</p></section>}
      <section className="query-boosts"><h4>Lexical boosts in the actual pipeline</h4>{config.lexicalBoosts?.length ? config.lexicalBoosts.map((boost,i)=><article key={i}><strong>{boost.boost}× <span>{boost.operator} · {boost.paths.join(' + ')}</span></strong><p>{boost.query}</p></article>):<p>No extra lexical boosts for this profile.</p>}</section>
      <details className="raw-query"><summary>Raw query configuration</summary><pre>{JSON.stringify(config,null,2)}</pre></details>
    </> : <p>Preparing the selected retrieval profile…</p>}
    {plan?.claimFacts?.map(c=><div className="claim-fact" key={c.claimId}><strong>{c.claimId}</strong><span>{money(c.memberPaidCents)} recorded member payment</span><small>Fill date {String(c.serviceDate).slice(0,10)} · recorded rule {c.recordedRuleId||'not recorded'}</small><pre>{JSON.stringify(c.components,null,2)}</pre></div>)}
    {plan?.claimFacts?.some(c=>String(c.serviceDate).slice(0,10)!==asOf)&&<p className="date-note">The selected rule date differs from one or more claim dates. Resolve each claim's applicable versions independently when comparing fills.</p>}
  </div>;
}
