(function () {
// Run in authenticated mongosh. Dry-run by default; set CONTEXT_KNOWLEDGE_GRAPH_APPLY=true to apply.
// No credentials are stored in this file. Operational documents are never modified.
const crypto = require('crypto');
const base = db.getSiblingDB('context_knowledge_graph_demo');
if (['claims_context','members_context','drugs_context','plans_context','prior_authorizations_context'].some(name => base.getCollection(name).findOne({contextSchemaVersion:2}))) {
  throw Error('Historical v1 migration disabled for root-shaped context. Use context-knowledge-graph-runtime/scripts/migrate_context_mirrors.py.');
}
const migration = 'domain-context-v1';
const mappings = [ ['claims','claims_context','claimRef'], ['members','members_context','memberRef'], ['drugs','drugs_context','drugRef'], ['plans','plans_context','planRef'], ['prior_authorizations','prior_authorizations_context','priorAuthorizationRef'] ];
const fingerprint = x => crypto.createHash('sha256').update(EJSON.stringify(x)).digest('hex');
const clone = x => EJSON.parse(EJSON.stringify(x));
const assert = (ok,msg) => { if (!ok) throw Error(msg); };
const originals = Object.fromEntries(mappings.map(([n]) => [n,base.getCollection(n).find().sort({_id:1}).toArray()]));
assert(originals.claims.length > 0,'No source claims');
const legacyName = base.getCollectionNames().includes('decision_traces') ? 'decision_traces' : null;
const traces = legacyName ? base.decision_traces.find().toArray() : base.getSiblingDB('context_knowledge_graph_archive').decision_traces.find().toArray();
const stamp = new Date();
const pending = [];
for (const [sourceName,targetName,refField] of mappings) {
  for (const raw of originals[sourceName]) {
    const snapshot = clone(raw);
    delete snapshot._id;
    delete snapshot.context;
    delete snapshot.provenance;
    const links = {};
    for (const [field,kind] of [['memberRef','member'],['drugRef','drug'],['planRef','plan'],['paRef','priorAuthorization']]) {
      if (raw[field] != null) links[kind] = {ref:raw[field],method:'source-reference',verificationStatus:'not-verified',evidenceRefs:[{collection:sourceName,documentId:raw._id,fieldPath:field}]};
    }
    const missing = sourceName === 'claims' ? ['memberRef','drugRef','planRef'].filter(k=>raw[k]==null) : [];
    const linkedTraces = sourceName === 'claims' ? traces.filter(t=>t.claimRef===raw._id || t.businessObject?.id===raw._id || t._id===raw.adjudication?.decisionTraceRef) : [];
    const value = {
      _id:'context-'+raw._id,
      [refField]:raw._id,
      schemaVersion:1,
      revision:1,
      source:{database:base.getName(),collection:sourceName,documentId:raw._id,sourceVersion:raw.version??null,contentHash:fingerprint(raw),provenance:raw.provenance??null,observedAt:stamp},
      operationalSnapshot:snapshot,
      resolvedRelationships:links,
      investigation:{status:'not_started',hasSignificantFindings:false,findings:[],missingEvidence:missing.map(field=>({type:'missing-direct-reference',field})),...(linkedTraces.length?{recordedSourceEvidence:linkedTraces.map(t=>({origin:'synthetic-source-artifact',legacyTraceId:t._id,artifact:t}))}:{})},
      explanation:{status:'not_generated',summary:null,evidenceRefs:[]},
      freshness:{assembledAt:stamp,sourceCheckedAt:stamp,dependenciesCheckedAt:null,status:'source-snapshot-only'},
      migration:{id:migration,createdAt:stamp}
    };
    if(raw.context) value.metadata={sourceAnnotations:{value:clone(raw.context),sourceRef:{collection:sourceName,documentId:raw._id,fieldPath:'context'},origin:'preexisting-fixture'}};
    if(sourceName==='plans') value.policyRefs=['policy-'+raw._id];
    pending.push({collection:targetName,value});
  }
}
for(const p of originals.plans) {
  pending.push({collection:'rules_policies',value:{
    _id:'policy-'+p._id,policyKey:'plan-benefit-'+p.planCode,version:p.version,type:'plan-benefit-rule-reference',status:'synthetic-fixture',
    scope:{planCode:p.planCode,planRef:p._id},effectiveFrom:p.validFrom,effectiveTo:p.validTo??null,
    content:{summary:'Synthetic benefit configuration for '+p.planCode+', version '+p.version+'. Exact amounts and conditions remain authoritative in the referenced plan.',sourceFieldPath:'benefit'},
    authority:{kind:'derived-source-reference',sourceCollection:'plans',sourceRef:p._id,sourceVersion:p.version,sourceContentHash:fingerprint(p),isExecutable:false},
    provenance:{synthetic:true,migrationId:migration,observedAt:stamp},
    migration:{id:migration,createdAt:stamp}
  }});
}
// Refuse to replace prior context, including enrichments created by other writers.
for(const {collection,value} of pending) {
  const old=base.getCollection(collection).findOne({_id:value._id});
  if(old) {
    assert(old.migration?.id===migration,'Unowned context conflict: '+value._id);
    const oldHash=old.source?.contentHash??old.authority?.sourceContentHash;
    const newHash=value.source?.contentHash??value.authority?.sourceContentHash;
    assert(oldHash===newHash,'Source changed since migration: '+value._id);
  }
}
const archive=base.getSiblingDB('context_knowledge_graph_archive');
const evaluation=base.getSiblingDB('context_knowledge_graph_eval');
for(const [from,target] of [['decision_traces',archive],['expected_answers',evaluation]]) {
  if(base.getCollectionNames().includes(from)) assert(!target.getCollectionNames().includes(from),'Archive destination already exists: '+target.getName()+'.'+from);
}
printjson({mode:globalThis.CONTEXT_KNOWLEDGE_GRAPH_APPLY===true?'apply':'dry-run',sourceCounts:Object.fromEntries(Object.entries(originals).map(([k,v])=>[k,v.length])),contextDocuments:pending.length,legacyTraces:traces.length,moves:['context_knowledge_graph_demo.decision_traces -> context_knowledge_graph_archive.decision_traces','context_knowledge_graph_demo.expected_answers -> context_knowledge_graph_eval.expected_answers']});
if(globalThis.CONTEXT_KNOWLEDGE_GRAPH_APPLY===true) {
  const s=base.getMongo().startSession();
  try {
    s.withTransaction(()=>{
      const tx=s.getDatabase(base.getName());
      for(const {collection,value} of pending) tx.getCollection(collection).updateOne({_id:value._id},{$setOnInsert:value},{upsert:true});
    });
  } finally {s.endSession();}
  // Verify all writes before moving legacy artifacts.
  for(const [name,rows] of Object.entries(originals)) {
    const current=base.getCollection(name).find().sort({_id:1}).toArray();
    assert(fingerprint(current)===fingerprint(rows),'Operational source changed: '+name);
  }
  for(const {collection,value} of pending) {
    const actual=base.getCollection(collection).findOne({_id:value._id});
    assert(actual,'Missing target: '+value._id);
    if(value.source) assert(actual.source.contentHash===value.source.contentHash,'Snapshot hash mismatch');
  }
  for(const t of traces) {
    const claim=originals.claims.find(c=>t.claimRef===c._id || t.businessObject?.id===c._id || t._id===c.adjudication?.decisionTraceRef);
    assert(claim,'Orphan source trace: '+t._id);
    const ctx=base.claims_context.findOne({claimRef:claim._id});
    const preserved=ctx.investigation.recordedSourceEvidence.find(e=>e.legacyTraceId===t._id);
    assert(preserved && fingerprint(preserved.artifact)===fingerprint(t),'Trace preservation failed: '+t._id);
  }
  for(const [from,target] of [['decision_traces',archive],['expected_answers',evaluation]]) {
    if(base.getCollectionNames().includes(from)) {
      const before=base.getCollection(from).find().sort({_id:1}).toArray();
      const result=base.getSiblingDB('admin').runCommand({renameCollection:base.getName()+'.'+from,to:target.getName()+'.'+from,dropTarget:false});
      assert(result.ok===1,'Archive move failed: '+from);
      assert(fingerprint(before)===fingerprint(target.getCollection(from).find().sort({_id:1}).toArray()),'Archive content mismatch: '+from);
    }
  }
  // Exact-match indexes; Search / Vector Search deployment is intentionally separate.
  for(const [,target,ref] of mappings) base.getCollection(target).createIndex({[ref]:1},{unique:true,name:'ux_domain_object'});
  base.rules_policies.createIndex({'scope.planRef':1,version:1},{unique:true,name:'ux_plan_rule_version'});
  base.rules_policies.createIndex({policyKey:1,effectiveFrom:1},{name:'ix_policy_effective'});
  printjson({verified:true,operationalDocumentsUnchanged:true,sourceEvidencePreserved:true,collections:base.getCollectionNames().sort().map(n=>({name:n,count:base.getCollection(n).countDocuments({})})),archiveTraces:archive.decision_traces.countDocuments({}),evaluationCases:evaluation.expected_answers.countDocuments({})});
}

})();
