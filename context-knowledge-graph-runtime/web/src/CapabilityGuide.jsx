import React, { useState } from 'react';

const examples = [
  { id: 'compare', label: 'Compare two copays', question: 'Why is my copay $50 instead of $10 like last time?', domains: ['Claim', 'Member', 'Plan', 'Drug', 'PA if relevant'], steps: ['Resolve both fills and their dates', 'Compare benefits, drug tiers, and pricing inputs', 'Check applicable changes and missing evidence'], rules: ['Effective plan and formulary versions', 'Copay / coinsurance and applicable limits', 'Exceptions only when their scope supports a pricing effect'] },
  { id: 'oopm', label: 'Investigate OOP maximum', question: 'Why am I still paying coinsurance after reaching my OOPM?', domains: ['Claim', 'Member', 'Plan'], steps: ['Resolve the fill and benefit year', 'Check accumulator timing and eligible amounts', 'Test the question’s premise against recorded evidence'], rules: ['Individual / family maximum applicability', 'Amounts that count toward the maximum', 'Cost sharing before and after the threshold'] },
  { id: 'pa', label: 'Explain PA impact', question: 'My prior authorization was approved. Why do I still owe a copay?', domains: ['Claim', 'PA', 'Plan', 'Drug', 'Member'], steps: ['Resolve the claim and matching authorization', 'Check approval dates, product, and scope', 'Separate coverage approval from a cost-sharing exception'], rules: ['Authorization applicability and coverage conditions', 'Plan cost-sharing requirements', 'Explicit exceptions or overrides, if supported'] },
];
const catalog = [
  ['Verify coverage eligibility', 'Member · Plan · Claim'],
  ['Explain member payment', 'Claim · Plan · Drug · Member'],
  ['Explain drug tier placement', 'Drug · Plan · Claim'],
  ['Explain allowed drug cost', 'Claim · Drug · Plan'],
  ['Investigate deductible / OOP status', 'Member · Plan · Claim'],
  ['Explain prior authorization impact', 'PA · Plan · Drug · Claim'],
  ['Compare pharmacy / channel costs', 'Claim · Plan · Drug'],
  ['Explain a utilization rejection', 'Claim · Drug · Plan · PA'],
  ['Reconcile a reversed or adjusted claim', 'Claim · Member · Plan'],
  ['Validate a client benefit configuration', 'Plan · Claim + approved client requirements'],
];

export default function CapabilityGuide() {
  const [selected, setSelected] = useState('compare');
  const example = examples.find(x => x.id === selected);
  return <section className="capability-guide" aria-label="Capabilities and data domains">
    <header><div><div className="eyebrow">BUSINESS CAPABILITIES / DATA DOMAINS</div><h2>What we need to do. What we need to know.</h2></div><span className="capability-badge">Design examples</span></header>
    <p className="capability-intro">Claim, Member, Drug, Plan, and PA organize the information. A capability describes a business outcome, such as explaining a payment. One capability can use several domains; the same domain can support many capabilities.</p>
    <div className="capability-options" aria-label="Capability examples">{examples.map(x => <button key={x.id} aria-pressed={selected === x.id} onClick={() => setSelected(x.id)}>{x.label}</button>)}</div>
    <div className="capability-question"><small>CAPABILITY / THE CUSTOMER’S QUESTION</small><h3>{example.question}</h3></div>
    <div className="capability-mapping">
      <article><span className="eyebrow">PROCEDURE</span><h3>How to investigate</h3><ol>{example.steps.map(step => <li key={step}>{step}</li>)}</ol><p>Reusable procedural memory can organize this investigation.</p></article>
      <article><span className="eyebrow">RULES</span><h3>Which conditions apply</h3><ul>{example.rules.map(rule => <li key={rule}>{rule}</li>)}</ul><p>Retrieve effective rule versions and follow declared dependencies. Evidence must establish applicability.</p></article>
      <article><span className="eyebrow">DATA DOMAINS</span><h3>Where the evidence lives</h3><div className="domain-chips">{example.domains.map(domain => <span key={domain}>{domain}</span>)}</div><p>Shared domain-context collections supply source-shaped evidence and attributed enrichment. Refresh from source when needed.</p></article>
    </div>
    <p className="capability-takeaway"><strong>The procedure organizes the investigation. The rules determine which calculation applies.</strong> Domain evidence supplies the inputs and the recorded outcome. These are complementary responsibilities, with no one-to-one mapping to agents or collections.</p>
    <details className="capability-catalog"><summary>Explore 10 example capabilities and their data domains</summary><p>Illustrative scope for planning; these are not ten implemented agents. Additional evidence may be needed beyond the five initial domains.</p><table><thead><tr><th>Business capability</th><th>Primary data domains / evidence</th></tr></thead><tbody>{catalog.map(([capability, domains]) => <tr key={capability}><td>{capability}</td><td>{domains}</td></tr>)}</tbody></table></details>
  </section>;
}
