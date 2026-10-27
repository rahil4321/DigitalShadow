import React, { useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, CheckCircle2,
  ChevronDown, ChevronRight, CircleHelp, ClipboardList, Download, ExternalLink,
  FileSearch, FlaskConical, Globe2, Layers3, LoaderCircle, Play, RefreshCw, Search,
  ShieldCheck, SlidersHorizontal, Sparkles, Target, TrendingUp, Wallet, XCircle,
} from 'lucide-react';
import { apiFetch } from './apiClient.js';
import './ScenarioStudio.css';

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\/+$/, '');

const DEFAULT_SCENARIO = {
  scenario_name: 'Port disruption · urgent customer order',
  description: 'I run a small electronics distributor. A possible port disruption could delay a laptop shipment. I have $6,000 in cash, need to deliver 10 laptops within 4 days, and face a $500 late-cancellation penalty. Compare a faster supplier with a slower alternative, and minimize the chance of missing the deadline without running out of cash.',
  starting_cash: 6000,
  sku_name: 'LAPTOP',
  starting_inventory_qty: 0,
  unit_cost: 500,
  unit_price: 1000,
  order_quantity: 10,
  deadline_days: 4,
  penalty_per_late_day: 500,
  primary_supplier_name: 'Express Supplier',
  primary_supplier_lead_time_days: 2,
  primary_supplier_reliability: 0.98,
  primary_supplier_fee_per_unit: 0,
  alternate_supplier_name: 'Standard Supplier',
  alternate_supplier_lead_time_days: 6,
  alternate_supplier_reliability: 0.8,
  alternate_supplier_fee_per_unit: 0,
  customer_advance_amount: 2000,
  customer_advance_acceptance_probability: 0.8,
  sla_guardrail_pct: 70,
  solvency_guardrail_pct: 95,
  objective: 'balanced',
  simulation_horizon_days: 14,
  num_runs: 1000,
  research_query: '',
};

const MONEY_FIELDS = new Set([
  'starting_cash', 'unit_cost', 'unit_price', 'penalty_per_late_day', 'customer_advance_amount',
  'primary_supplier_fee_per_unit', 'alternate_supplier_fee_per_unit',
]);
const INT_FIELDS = new Set([
  'starting_inventory_qty', 'order_quantity', 'deadline_days', 'primary_supplier_lead_time_days',
  'alternate_supplier_lead_time_days', 'simulation_horizon_days', 'num_runs',
]);
const PROB_FIELDS = new Set(['primary_supplier_reliability', 'alternate_supplier_reliability', 'customer_advance_acceptance_probability']);
const PCT_FIELDS = new Set(['sla_guardrail_pct', 'solvency_guardrail_pct']);

function money(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value));
}
function pct(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return `${Number(value).toFixed(1)}%`;
}
function ci(interval) {
  if (!interval || !Number.isFinite(Number(interval.lower)) || !Number.isFinite(Number(interval.upper))) return 'not available';
  return `${pct(interval.lower)}–${pct(interval.upper)}`;
}
function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}
function formatProvenanceValue(item) {
  const field = typeof item?.field === 'string' ? item.field : '';
  const value = item?.value;
  if (typeof value !== 'number' || !Number.isFinite(value)) return String(value ?? 'Not provided');
  if (field.endsWith('_probability') || field.endsWith('_reliability')) return pct(value * 100);
  if (field.includes('cash') || field.includes('cost') || field.includes('price') || field.includes('fee')) return money(value, 2);
  return value.toLocaleString();
}
function errorMessage(error) {
  const detail = error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => `${(item.loc || []).slice(-1)[0] || 'Field'}: ${item.msg}`).join('; ');
  return error?.message || 'The request failed. Check that the backend is running and try again.';
}
async function api(path, options = {}) {
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  let body;
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) throw new Error(errorMessage(body) || `Request failed (${response.status})`);
  return body;
}

function StatusTag({ status, children }) {
  const live = ['live_success', 'live_partial', 'live_success_with_fallback', 'partial_live_with_fallback', 'live_success_with_fallback_added'].includes(status);
  const fail = ['fallback_after_error', 'fallback_invalid_output', 'no_results'].includes(status);
  return <span className={`sc-tag ${live ? 'is-live' : fail ? 'is-alert' : 'is-muted'}`}><i />{children || (live ? 'LIVE' : fail ? 'FALLBACK' : 'DEMO / NOT CONFIGURED')}</span>;
}

function Field({ label, name, value, onChange, type = 'number', min, max, step, suffix, help, options, placeholder }) {
  const id = `scenario-${name}`;
  return <div className="sc-field">
    <label htmlFor={id}>{label}</label>
    {options ? <select id={id} value={value} onChange={(event) => onChange(name, event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select> : <div className="sc-input-wrap">
      <input id={id} type={type === 'number' ? 'text' : type} inputMode={type === 'number' ? 'decimal' : undefined}
        value={value ?? ''} min={min} max={max} step={step} placeholder={placeholder}
        onChange={(event) => onChange(name, event.target.value)} />
      {suffix && <span>{suffix}</span>}
    </div>}
    {help && <small>{help}</small>}
  </div>;
}

function SectionTitle({ number, icon: Icon, title, detail }) {
  return <div className="sc-section-title"><span className="sc-section-number">{number}</span><div className="sc-section-icon"><Icon size={17} /></div><div><h3>{title}</h3><p>{detail}</p></div></div>;
}

function Metric({ label, value, note, tone = 'normal', icon: Icon }) {
  return <article className={`sc-metric sc-tone-${tone}`}><div className="sc-metric-label">{Icon && <Icon size={14} />}<span>{label}</span></div><strong>{value}</strong>{note && <p>{note}</p>}</article>;
}

export default function ScenarioStudio({ onOpenDemo }) {
  const [scenario, setScenario] = useState(DEFAULT_SCENARIO);
  const [draftInfo, setDraftInfo] = useState(null);
  const [evidence, setEvidence] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [audit, setAudit] = useState(null);
  const [expandedAssumptions, setExpandedAssumptions] = useState(false);

  const patch = (name, raw) => {
    setScenario((current) => {
      // Keep numeric edits as strings until submit so users can type decimals and clear fields.
      const value = raw;
      const next = { ...current, [name]: value };
      // If the business description changes, discard a stale scenario-specific search query.
      // The research endpoint will use the current description until the user enters a focused query.
      if (name === 'description') next.research_query = '';
      if (name === 'deadline_days' && Number(next.simulation_horizon_days) < Number(value)) next.simulation_horizon_days = value;
      return next;
    });
    if (name === 'description' || name === 'research_query') {
      setEvidence(null);
      setDraftInfo(null);
    }
    setResult(null);
    setAudit(null);
  };

  const reset = () => {
    setScenario(DEFAULT_SCENARIO);
    setDraftInfo(null);
    setEvidence(null);
    setResult(null);
    setAudit(null);
    setError('');
    setNotice('Example scenario restored. Review its assumptions before running it.');
  };

  const draft = async () => {
    setBusy('draft'); setError(''); setNotice('');
    try {
      const body = await api('/api/scenario/draft', { method: 'POST', body: JSON.stringify({ description: scenario.description, research_query: scenario.research_query }) });
      setScenario((current) => ({ ...current, ...body.draft, research_query: current.research_query || body.draft.research_query || '' }));
      setDraftInfo(body.integration);
      setResult(null); setAudit(null);
      setNotice(body.notice || 'Draft ready. Check the editable assumptions before simulation.');
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };

  const research = async () => {
    setBusy('research'); setError(''); setNotice(''); setEvidence(null); setResult(null); setAudit(null);
    try {
      const body = await api('/api/scenario/research', { method: 'POST', body: JSON.stringify({ description: scenario.description, research_query: scenario.research_query, max_sources: 6 }) });
      setEvidence(body);
      setResult(null); setAudit(null);
      if (body.evidence_used) setNotice(`Tavily returned ${body.sources?.length || 0} sources; ${body.sources?.filter((source) => source.extracted).length || 0} page(s) were extracted. Review the evidence below before simulating.`);
      else setNotice('No live evidence is attached. The simulator can still run, but every external-context assumption stays illustrative.');
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };

  const simulate = async () => {
    setBusy('simulate'); setError(''); setNotice(''); setAudit(null);
    try {
      // Ensure valid numeric inputs rather than submitting half-edited empty strings.
      const cleaned = { ...scenario };
      [...MONEY_FIELDS, ...INT_FIELDS, ...PROB_FIELDS, ...PCT_FIELDS].forEach((key) => {
        if (cleaned[key] === '' || cleaned[key] === null || !Number.isFinite(Number(cleaned[key]))) throw new Error(`Enter a valid number for ${key.replaceAll('_', ' ')}.`);
        cleaned[key] = Number(cleaned[key]);
      });
      const body = await api('/api/scenario/simulate', { method: 'POST', body: JSON.stringify({ scenario: cleaned, evidence: evidence || {} }) });
      setScenario(cleaned);
      setResult(body);
      setNotice(body.assumptions?.decision_policy || 'Simulation complete. Review the guardrails and assumptions before relying on the recommendation.');
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };

  const replayApproval = async () => {
    if (!result?.simulation_id || !result?.best_strategy_data?.strategy_id) return;
    setBusy('replay'); setError('');
    try {
      const body = await api('/api/execute', { method: 'POST', body: JSON.stringify({ simulation_id: result.simulation_id, strategy_id: result.best_strategy_data.strategy_id }) });
      setAudit(body);
      setNotice('Simulated approval recorded in the audit trail. No supplier or customer was contacted.');
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };

  const exportBrief = () => {
    if (!result) return;
    const lines = [
      `# Digital Shadow decision brief — ${result.scenario.scenario_name}`,
      '', `Generated: ${new Date().toISOString()}`, `Simulation ID: ${result.simulation_id}`,
      '', '## Recommendation', `**${result.best_strategy}**`, result.assumptions.decision_policy,
      '', '## Scenario', result.scenario.description,
      `- Starting cash: ${money(result.scenario.starting_cash, 2)}`,
      `- Order: ${result.scenario.order_quantity} ${result.scenario.sku_name}`,
      `- Unit cost / sale price: ${money(result.scenario.unit_cost, 2)} / ${money(result.scenario.unit_price, 2)}`,
      `- Supplier premiums per unit: ${result.scenario.primary_supplier_name} ${money(result.scenario.primary_supplier_fee_per_unit, 2)}; ${result.scenario.alternate_supplier_name} ${money(result.scenario.alternate_supplier_fee_per_unit, 2)}`,
      `- Deadline: Day ${result.scenario.deadline_days}`,
      `- Objective: ${result.scenario.objective}`,
      '', '## Strategy comparison',
      ...result.strategies.map((strategy) => `- **${strategy.name}** — expected operating profit ${money(strategy.expected_profit, 2)}; on-time success ${pct(strategy.sla_success_probability)} (95% Wilson CI ${ci(strategy.sla_success_ci95)}); non-negative ending cash ${pct(strategy.solvency_probability)} (95% Wilson CI ${ci(strategy.solvency_ci95)}); p05 cash ${money(strategy.p05_cash, 2)}; worst observed cash ${money(strategy.worst_case_cash, 2)}; guardrails ${strategy.guardrail_status || 'see assumptions'}.`),
      '', '## Decision tipping points',
      result.decision_sensitivity?.available ? `Maximum tested alternate-supplier lead time passing the SLA lower-bound guardrail: ${result.decision_sensitivity.maximum_lead_time_meeting_sla_guardrail ?? 'none'}. ${result.decision_sensitivity.note}` : 'Alternate lead-time sensitivity unavailable for this scenario.',
      result.cash_reserve_sensitivity?.available ? `Estimated primary-supplier starting-cash threshold: ${money(result.cash_reserve_sensitivity.minimum_starting_cash_estimate, 2)}; cash lower bound ${pct(result.cash_reserve_sensitivity.nonnegative_cash_ci95?.lower)} against guardrail ${pct(result.cash_reserve_sensitivity.cash_guardrail_lower_bound_pct)}. ${result.cash_reserve_sensitivity.method}` : `Cash-reserve sensitivity unavailable: ${result.cash_reserve_sensitivity?.message || 'not computed'}`,
      '', '## Evidence', result.evidence?.summary || 'No evidence summary available.',
      ...(result.evidence?.sources || []).map((source) => `- ${source.title} (${source.published_date || 'date not listed'}): ${source.url}`),
      '', '## Evidence-to-assumption mapping',
      ...(result.evidence_to_assumption_map || []).map((item) => `- ${item.title}: may inform ${item.can_inform.join(', ')}; does not automatically verify ${item.does_not_automatically_verify.join(', ')}; numeric model input changed: ${item.numeric_model_input_changed_by_source}.`),
      '', '## Material assumptions',
      ...Object.entries(result.assumptions).map(([key, value]) => `- ${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`),
      '', '## Limitations', 'All simulation results are conditional on the input assumptions. Monte Carlo sampling uncertainty is not real-world forecast certainty. This prototype does not contact suppliers or customers and does not place orders.',
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'digital-shadow-decision-brief.md'; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const strategyRows = useMemo(() => result?.strategies || [], [result]);
  const best = result?.best_strategy_data;
  const srcs = evidence?.sources || result?.evidence?.sources || [];
  const evidenceStatus = evidence?.status || result?.evidence?.status;
  const liveSources = srcs.filter((source) => safeUrl(source.url));
  const strategyEligible = best && best.feasible && Number(best.sla_success_ci95?.lower ?? 0) >= Number(result.scenario.sla_guardrail_pct) && Number(best.solvency_ci95?.lower ?? 0) >= Number(result.scenario.solvency_guardrail_pct);
  const incomplete = Number(scenario.starting_cash) < 0 || Number(scenario.unit_cost) <= 0 || Number(scenario.unit_price) <= 0;
  const descriptionMentionsSupplierCost = /\b(cheaper|costlier|more expensive|less expensive|premium|surcharge|supplier fee|supplier quote|quoted price)\b/i.test(scenario.description);
  const supplierFeesDiffer = Number(scenario.primary_supplier_fee_per_unit || 0) !== Number(scenario.alternate_supplier_fee_per_unit || 0);

  return <main className="sc-shell">
    <div className="sc-grid-glow" />
    <div className="sc-container">
      <header className="sc-header">
        <a href="#top" className="sc-brand" onClick={(event) => event.preventDefault()}>
          <span className="sc-brand-mark"><Layers3 size={22} /></span>
          <span><small>OPERATIONAL DECISION INTELLIGENCE</small><strong>DIGITAL <em>SHADOW</em></strong></span>
        </a>
        <div className="sc-header-actions">
          <span className="sc-mode"><span /> SCENARIO STUDIO</span>
          <button className="sc-button sc-button-quiet" onClick={onOpenDemo}><Activity size={15} /> Classic demo <ArrowRight size={14} /></button>
        </div>
      </header>

      <section className="sc-hero" id="top">
        <div className="sc-hero-copy">
          <div className="sc-kicker"><span>FIELD NOTE 001</span><i /> FROM EVIDENCE TO ACTION</div>
          <h1>Rehearse the<br /><span>business decision</span><br />before it costs you.</h1>
          <p>Describe a disruption in plain language. Investigate the live web, turn the evidence into explicit stress assumptions, and simulate which action best protects cash and delivery.</p>
          <div className="sc-hero-chips"><span><Globe2 size={13} /> Tavily research</span><span><FlaskConical size={13} /> Monte Carlo futures</span><span><ShieldCheck size={13} /> Guardrail-first policy</span></div>
        </div>
        <div className="sc-hero-graphic" aria-hidden="true">
          <div className="sc-orbit sc-orbit-a" /><div className="sc-orbit sc-orbit-b" /><div className="sc-orbit sc-orbit-c" />
          <div className="sc-orb-core"><Layers3 size={28} /><span>DECISION<br />ENGINE</span></div>
          <span className="sc-orb-label sc-orb-label-a">EVIDENCE</span><span className="sc-orb-label sc-orb-label-b">SIMULATION</span><span className="sc-orb-label sc-orb-label-c">ACTION</span>
        </div>
      </section>

      {error && <div className="sc-alert sc-alert-error"><AlertTriangle size={17} /><div><strong>Something needs attention</strong><span>{error}</span></div><button aria-label="Dismiss error" onClick={() => setError('')}><XCircle size={16} /></button></div>}
      {notice && !error && <div className="sc-alert sc-alert-info"><CheckCircle2 size={17} /><span>{notice}</span><button aria-label="Dismiss notice" onClick={() => setNotice('')}><XCircle size={16} /></button></div>}

      <div className="sc-workflow-strip">
        <div className={`sc-workflow-step ${draftInfo ? 'is-done' : 'is-active'}`}><span>01</span><div><strong>Frame the scenario</strong><small>Describe the business problem</small></div></div>
        <div className={`sc-workflow-step ${evidence?.evidence_used ? 'is-done' : ''}`}><span>02</span><div><strong>Investigate</strong><small>Search + extract source evidence</small></div></div>
        <div className={`sc-workflow-step ${result ? 'is-done' : ''}`}><span>03</span><div><strong>Stress-test</strong><small>Compare alternative futures</small></div></div>
        <div className={`sc-workflow-step ${result ? 'is-active' : ''}`}><span>04</span><div><strong>Decide</strong><small>Evidence-backed decision brief</small></div></div>
      </div>

      <section className="sc-panel sc-scenario-panel">
        <SectionTitle number="01" icon={ClipboardList} title="Describe the business situation" detail="Start in natural language. Then confirm the parameters the simulation will actually use." />
        <div className="sc-description-field">
          <label htmlFor="scenario-description">What is happening, and what decision do you need to make?</label>
          <textarea id="scenario-description" value={scenario.description} maxLength={3000} onChange={(event) => patch('description', event.target.value)} placeholder="Describe your inventory, cash, deadline, disruption and the decision you need to make…" />
          <div className="sc-textarea-footer"><span>Be specific about the product, money, deadline and operational risk.</span><span>{scenario.description.length}/3,000</span></div>
        </div>
        <div className="sc-action-row">
          <button className="sc-button sc-button-secondary" onClick={reset}><RefreshCw size={15} /> Reset example</button>
          <div className="sc-action-spacer" />
          {draftInfo && <StatusTag status={draftInfo.status}>{draftInfo.used_live_model ? 'NEMOTRON LIVE' : 'LOCAL DRAFT'}</StatusTag>}
          <button className="sc-button sc-button-primary" onClick={draft} disabled={!!busy || scenario.description.trim().length < 10}>
            {busy === 'draft' ? <LoaderCircle className="sc-spin" size={16} /> : <Sparkles size={16} />}
            {busy === 'draft' ? 'Interpreting scenario…' : 'Interpret into editable fields'}
          </button>
        </div>
        <div className="sc-inline-disclaimer"><CircleHelp size={15} /><p><strong>Human-confirmed assumptions:</strong> AI extraction is a draft, not a fact-check. Values the description does not state are defaults until you confirm or replace them. Tavily evidence does not establish your specific supplier’s lead time unless the source explicitly provides it.</p></div>
      </section>

      <section className="sc-panel">
        <SectionTitle number="02" icon={SlidersHorizontal} title="Confirm the model inputs" detail="Every field below feeds the simulator. Change the example values to match your actual situation." />
        <div className="sc-input-groups">
          <div className="sc-input-group">
            <div className="sc-group-heading"><Wallet size={16} /><div><strong>Order economics</strong><small>Cash, inventory and unit-level economics</small></div></div>
            <div className="sc-fields-grid">
              <Field label="Scenario name" name="scenario_name" type="text" value={scenario.scenario_name} onChange={patch} />
              <Field label="SKU / product code" name="sku_name" type="text" value={scenario.sku_name} onChange={patch} help="Normalized to an uppercase SKU." />
              <Field label="Starting cash" name="starting_cash" value={scenario.starting_cash} onChange={patch} min={0} step="100" suffix="USD" />
              <Field label="Existing units in stock" name="starting_inventory_qty" value={scenario.starting_inventory_qty} onChange={patch} min={0} step="1" />
              <Field label="Unit purchase cost" name="unit_cost" value={scenario.unit_cost} onChange={patch} min="0.01" step="10" suffix="USD" />
              <Field label="Sale price per unit" name="unit_price" value={scenario.unit_price} onChange={patch} min="0.01" step="10" suffix="USD" />
              <Field label="Units the customer ordered" name="order_quantity" value={scenario.order_quantity} onChange={patch} min="1" max="1000" step="1" />
              <Field label="Late cancellation penalty" name="penalty_per_late_day" value={scenario.penalty_per_late_day} onChange={patch} min="0" step="50" suffix="USD/day" />
            </div>
          </div>
          <div className="sc-input-group">
            <div className="sc-group-heading"><Globe2 size={16} /><div><strong>Supplier assumptions</strong><small>Illustrative model inputs—not verified supplier ratings</small></div></div>
            <div className="sc-fields-grid">
              <Field label="Primary supplier name" name="primary_supplier_name" type="text" value={scenario.primary_supplier_name} onChange={patch} />
              <Field label="Alternate supplier name" name="alternate_supplier_name" type="text" value={scenario.alternate_supplier_name} onChange={patch} />
              <Field label="Primary lead time" name="primary_supplier_lead_time_days" value={scenario.primary_supplier_lead_time_days} onChange={patch} min="1" max="60" step="1" suffix="days" />
              <Field label="Alternate lead time" name="alternate_supplier_lead_time_days" value={scenario.alternate_supplier_lead_time_days} onChange={patch} min="1" max="60" step="1" suffix="days" />
              <Field label="Primary delivery-attempt reliability" name="primary_supplier_reliability" value={scenario.primary_supplier_reliability} onChange={patch} min="0" max="1" step="0.01" suffix="0–1" help="0.98 means 98% per attempt in the model." />
              <Field label="Alternate delivery-attempt reliability" name="alternate_supplier_reliability" value={scenario.alternate_supplier_reliability} onChange={patch} min="0" max="1" step="0.01" suffix="0–1" help="Not the same as on-time probability." />
              <Field label="Primary supplier premium per unit" name="primary_supplier_fee_per_unit" value={scenario.primary_supplier_fee_per_unit} onChange={patch} min="0" step="5" suffix="USD/unit" help="Optional expedite/handling premium; paid upfront and expensed immediately." />
              <Field label="Alternate supplier premium per unit" name="alternate_supplier_fee_per_unit" value={scenario.alternate_supplier_fee_per_unit} onChange={patch} min="0" step="5" suffix="USD/unit" help="Lets you compare a faster premium option with a lower-fee alternative." />
            </div>
            {descriptionMentionsSupplierCost && !supplierFeesDiffer && <div className="sc-alert sc-alert-info"><CircleHelp size={15} /><span>Your description mentions supplier prices or premiums, but both per-unit fee inputs are equal. Enter the actual incremental fee for each supplier; otherwise this run compares lead time and reliability without modeling a supplier price difference.</span></div>}
          </div>
          <div className="sc-input-group">
            <div className="sc-group-heading"><ShieldCheck size={16} /><div><strong>Risk, funding and objective</strong><small>Define success before the engine ranks options</small></div></div>
            <div className="sc-fields-grid">
              <Field label="Order deadline" name="deadline_days" value={scenario.deadline_days} onChange={patch} min="1" max="60" step="1" suffix="days" />
              <Field label="Simulation horizon" name="simulation_horizon_days" value={scenario.simulation_horizon_days} onChange={patch} min="1" max="60" step="1" suffix="days" help="Must be at least as long as the deadline." />
              <Field label="Customer advance option" name="customer_advance_amount" value={scenario.customer_advance_amount} onChange={patch} min="0" step="100" suffix="USD" />
              <Field label="Advance acceptance assumption" name="customer_advance_acceptance_probability" value={scenario.customer_advance_acceptance_probability} onChange={patch} min="0" max="1" step="0.05" suffix="0–1" help="Hypothetical customer response assumption." />
              <Field label="Minimum delivery-success lower bound" name="sla_guardrail_pct" value={scenario.sla_guardrail_pct} onChange={patch} min="0" max="100" step="1" suffix="%" />
              <Field label="Minimum non-negative-cash lower bound" name="solvency_guardrail_pct" value={scenario.solvency_guardrail_pct} onChange={patch} min="0" max="100" step="1" suffix="%" />
              <Field label="Business objective" name="objective" value={scenario.objective} onChange={patch} options={[
                { value: 'balanced', label: 'Balanced · profit after risk' },
                { value: 'maximize_profit', label: 'Maximize expected profit' },
                { value: 'protect_cash', label: 'Protect cash first' },
                { value: 'maximize_delivery', label: 'Maximize delivery success' },
              ]} />
              <Field label="Monte Carlo runs per strategy" name="num_runs" value={scenario.num_runs} onChange={patch} min="100" max="5000" step="100" help="Use 1,000 for demo speed; more runs cost more compute." />
            </div>
          </div>
          <div className="sc-input-group sc-research-group">
            <div className="sc-group-heading"><Search size={16} /><div><strong>Tavily research focus</strong><small>Three complementary search angles plus targeted extraction</small></div></div>
            <Field label="Research query / incident, route or region" name="research_query" type="text" value={scenario.research_query} onChange={patch} help="Optional. Leave blank to search for the current scenario description; add named ports, routes, suppliers or events to narrow the search." />
            <div className="sc-research-actions">
              <button className="sc-button sc-button-secondary" onClick={research} disabled={!!busy || scenario.description.trim().length < 10}>
                {busy === 'research' ? <LoaderCircle className="sc-spin" size={16} /> : <Search size={15} />}
                {busy === 'research' ? 'Researching live sources…' : 'Research with Tavily'}
              </button>
              <span>Uses live retrieval when your Tavily key is configured. No key? Simulation remains available in labelled demo mode.</span>
            </div>
          </div>
        </div>
        <div className="sc-simulation-bar">
          <div><span className="sc-simulation-indicator"><Activity size={16} /></span><div><strong>Ready to stress-test the decision</strong><small>{evidence?.evidence_used ? `${liveSources.length} evidence sources attached` : 'No live evidence attached yet; assumptions will be labelled as illustrative.'}</small></div></div>
          <button className="sc-button sc-button-primary sc-button-large" onClick={simulate} disabled={!!busy || incomplete}>
            {busy === 'simulate' ? <LoaderCircle className="sc-spin" size={17} /> : <Play size={16} fill="currentColor" />}
            {busy === 'simulate' ? 'Running alternate futures…' : 'Simulate and compare actions'} <ChevronRight size={16} />
          </button>
        </div>
      </section>

      {(evidence || result) && <section className="sc-panel sc-evidence-panel">
        <SectionTitle number="03" icon={FileSearch} title="Evidence ledger" detail="A transparent boundary between what the web reports and what the model assumes." />
        <div className="sc-evidence-summary">
          <div className="sc-evidence-icon"><Globe2 size={19} /></div>
          <div className="sc-evidence-summary-copy"><div className="sc-evidence-title-row"><strong>{evidence?.provider || result?.evidence?.provider || 'Tavily Search + Extract'}</strong><StatusTag status={evidenceStatus} /></div>
            <p>{evidence?.summary || result?.evidence?.summary || 'No research has run yet.'}</p>
            <small>{evidence?.retrieved_at || result?.evidence?.retrieved_at ? `Retrieved ${new Date(evidence?.retrieved_at || result?.evidence?.retrieved_at).toLocaleString()}` : 'No retrieval timestamp recorded'}</small>
          </div>
          <div className="sc-evidence-count"><strong>{liveSources.length}</strong><span>valid source links</span></div>
        </div>
        {evidence?.query_plan?.length > 0 && <details className="sc-query-plan"><summary><ChevronDown size={14} /> View the multi-query research plan</summary><ol>{evidence.query_plan.map((query, index) => <li key={`${index}-${query}`}>{query}</li>)}</ol></details>}
        <div className="sc-source-grid">
          {liveSources.length ? liveSources.map((source, index) => <article className="sc-source-card" key={`${source.url}-${index}`}>
            <div className="sc-source-meta"><span>SOURCE {String(index + 1).padStart(2, '0')}</span><span>{source.extracted ? 'PAGE EXTRACTED' : 'SEARCH SNIPPET'}</span></div>
            <h4>{source.title || source.domain || 'Untitled source'}</h4>
            <div className="sc-source-domain">{source.domain || new URL(source.url).hostname}{source.published_date ? ` · ${source.published_date}` : ''}</div>
            <p>{(source.content || 'No extractable content snippet was returned.').slice(0, 540)}{(source.content || '').length > 540 ? '…' : ''}</p>
            <div className="sc-source-footer"><span>{Number.isFinite(Number(source.score)) ? `Tavily relevance ${Number(source.score).toFixed(2)}` : 'Source metadata'}</span><a href={safeUrl(source.url)} target="_blank" rel="noreferrer">Open source <ExternalLink size={13} /></a></div>
          </article>) : <div className="sc-empty-evidence"><AlertTriangle size={18} /><div><strong>No live source evidence is attached</strong><p>Configure <code>TAVILY_API_KEY</code> in the backend environment, restart FastAPI, then run research again. The application will not invent citations or claim general shipping context proves a supplier ETA.</p></div></div>}
        </div>
        {result && <details className="sc-evidence-trace"><summary><ChevronDown size={14} /> See exactly how evidence is (and is not) connected to model inputs</summary>
          <p className="sc-trace-intro">Evidence is available to inform disruption context and mitigation ideas, but the workflow does not silently overwrite numerical business parameters from search results. No scenario input below is marked as directly source-verified.</p>
          {result.evidence_to_assumption_map?.length > 0 && <div className="sc-trace-source-list">{result.evidence_to_assumption_map.map((item, index) => <div key={`${item.url}-${index}`}><div><strong>{item.title}</strong><a href={safeUrl(item.url)} target="_blank" rel="noreferrer">Open source <ExternalLink size={12} /></a></div><p>May inform: {(item.can_inform || []).join(', ')}.</p><p>Does not automatically verify: {(item.does_not_automatically_verify || []).join(', ')}.</p><span>Numeric model input changed by this source: {item.numeric_model_input_changed_by_source ? 'Yes' : 'No'}</span></div>)}</div>}
          <div className="sc-provenance-grid">{(Array.isArray(result.assumption_provenance) ? result.assumption_provenance : []).filter((item) => item && typeof item === 'object').map((item, index) => { const field = typeof item.field === 'string' ? item.field : `assumption_${index + 1}`; return <div key={`${field}-${index}`}><span>{field.replaceAll('_', ' ')}</span><strong>{formatProvenanceValue({ ...item, field })}</strong><small>Editable input/default · not source-verified</small></div>; })}</div>
        </details>}
        <div className="sc-evidence-boundary"><ShieldCheck size={16} /><p><strong>Evidence boundary.</strong> These sources establish only what their content actually says. This app does not turn a broad news article into a fact about your supplier’s delivery reliability. Lead time, attempt reliability, sale price and customer acceptance remain explicit scenario assumptions unless directly evidenced and confirmed.</p></div>
      </section>}

      {result && best && <>
        <section className="sc-results-head">
          <div><div className="sc-kicker"><span>DECISION OUTPUT</span><i /> RUN {result.simulation_id.slice(0, 8).toUpperCase()}</div><h2>Here is the move the model would make.</h2><p>Recommendation first. Evidence, confidence bounds and alternatives remain inspectable.</p></div>
          <div className="sc-results-actions"><button className="sc-button sc-button-secondary" onClick={exportBrief}><Download size={15} /> Export decision brief</button><button className="sc-button sc-button-secondary" onClick={() => { setResult(null); setAudit(null); window.scrollTo({ top: 0, behavior: 'smooth' }); }}><RefreshCw size={15} /> Revise assumptions</button></div>
        </section>
        <section className="sc-recommendation-panel">
          <div className="sc-rec-main"><div className="sc-rec-badge"><Target size={17} /><span>RECOMMENDED STRATEGY</span></div><h3>{result.best_strategy}</h3><p>{best.explanation || result.assumptions.decision_policy}</p><div className="sc-rec-chips"><span><CheckCircle2 size={13} /> Python-validated action</span><span><Activity size={13} /> {Number(result.scenario.num_runs).toLocaleString()} runs per strategy</span><span><ShieldCheck size={13} /> {strategyEligible ? 'Passes guardrails' : 'Risk guardrail not met'}</span></div></div>
          <div className="sc-rec-score"><div className="sc-score-ring"><span>{pct(best.sla_success_probability)}</span><small>ON-TIME</small></div><span>95% Wilson interval</span><strong>{ci(best.sla_success_ci95)}</strong></div>
        </section>

        <section className="sc-analysis-card">
          <div className="sc-analysis-icon"><Sparkles size={18} /></div>
          <div className="sc-analysis-copy"><div className="sc-analysis-head"><strong>Decision narrative</strong><StatusTag status={result.integrations?.analyst?.status}>{result.integrations?.analyst?.used_live_model ? 'NEMOTRON EXPLANATION' : 'DETERMINISTIC EXPLANATION'}</StatusTag></div><p>{result.analysis || 'The Python decision policy selected the recommended strategy from the simulated outcomes.'}</p><small>Language-model commentary is explanatory only. Python owns feasibility, risk thresholds, financial calculations and the selected recommendation.</small></div>
        </section>

        {result.funding_diagnosis && <section className={`sc-funding-diagnosis sc-funding-${result.funding_diagnosis.status}`} aria-live="polite">
          <div className="sc-funding-heading"><div><span className="sc-kicker">FUNDING FEASIBILITY</span><h3>{result.funding_diagnosis.title}</h3><p>{result.funding_diagnosis.limitations}</p></div><div className="sc-funding-status">{result.funding_diagnosis.status.replaceAll('_', ' ')}</div></div>
          <div className="sc-funding-metrics">
            <div><span>Uncovered units</span><strong>{Number(result.funding_diagnosis.uncovered_quantity).toLocaleString()}</strong></div>
            <div><span>Least-cost supplier total</span><strong>{money(result.funding_diagnosis.estimated_procurement_cost, 2)}</strong><small>{result.funding_diagnosis.least_cost_supplier}</small></div>
            <div><span>Primary supplier total</span><strong>{money(result.funding_diagnosis.primary_supplier_total_cost, 2)}</strong></div>
            <div><span>Alternate supplier total</span><strong>{money(result.funding_diagnosis.alternate_supplier_total_cost, 2)}</strong></div>
            <div><span>Cash shortfall before advance</span><strong>{money(result.funding_diagnosis.cash_shortfall_before_advance, 2)}</strong></div>
            <div><span>Shortfall after advance if accepted</span><strong>{money(result.funding_diagnosis.funding_shortfall_after_advance, 2)}</strong></div>
          </div>
          <div className="sc-funding-next"><strong>Operational next steps</strong><ol>{(result.funding_diagnosis.next_steps || []).map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol></div>
        </section>}

        <section className="sc-metric-grid">
          <Metric label="Expected operating profit" value={money(best.expected_profit, 2)} note="Mean across simulated runs; not a guaranteed return." icon={TrendingUp} tone={Number(best.expected_profit) >= 0 ? 'good' : 'bad'} />
          <Metric label="Non-negative ending cash" value={pct(best.solvency_probability)} note={`95% Wilson interval ${ci(best.solvency_ci95)}`} icon={Wallet} tone={Number(best.solvency_ci95?.lower) >= Number(result.scenario.solvency_guardrail_pct) ? 'good' : 'bad'} />
          <Metric label="5th-percentile ending cash" value={money(best.p05_cash, 2)} note="Nearest-rank p05 in these sampled outcomes." icon={ArrowDownRight} tone={Number(best.p05_cash) < 0 ? 'bad' : 'normal'} />
          <Metric label="Worst observed ending cash" value={money(best.worst_case_cash, 2)} note="Worst outcome in the sample, not a theoretical bound." icon={AlertTriangle} tone={Number(best.worst_case_cash) < 0 ? 'bad' : 'normal'} />
        </section>

        <section className="sc-panel sc-comparison-panel">
          <SectionTitle number="04" icon={GitCompareIcon} title="Compare alternative futures" detail="All choices use the same business state. Guardrails use the lower bound of 95% Wilson intervals, not only the point estimate." />
          <div className="sc-table-wrap"><table className="sc-strategy-table"><thead><tr><th>Strategy</th><th>Expected profit</th><th>On time · 95% CI</th><th>Cash ≥ $0 · 95% CI</th><th>p05 cash</th><th>Policy result</th></tr></thead><tbody>
            {strategyRows.map((strategy) => {
              const slaLower = Number(strategy.sla_success_ci95?.lower ?? 0);
              const cashLower = Number(strategy.solvency_ci95?.lower ?? 0);
              const qualifies = strategy.feasible && slaLower >= Number(result.scenario.sla_guardrail_pct) && cashLower >= Number(result.scenario.solvency_guardrail_pct);
              return <tr key={strategy.strategy_id} className={strategy.strategy_id === best.strategy_id ? 'is-winner' : ''}>
                <td><strong>{strategy.name}</strong>{strategy.strategy_id === best.strategy_id && <small>Recommended</small>}{!strategy.feasible && <small>{strategy.rejection_reason}</small>}</td>
                <td className={Number(strategy.expected_profit) < 0 ? 'is-negative' : ''}>{money(strategy.expected_profit, 2)}</td>
                <td>{pct(strategy.sla_success_probability)}<small>{ci(strategy.sla_success_ci95)}</small></td>
                <td>{pct(strategy.solvency_probability)}<small>{ci(strategy.solvency_ci95)}</small></td>
                <td>{money(strategy.p05_cash, 2)}</td>
                <td><span className={`sc-policy-pill ${qualifies ? 'is-pass' : 'is-watch'}`}>{qualifies ? 'GUARDRAILS PASS' : strategy.feasible ? 'RISK NOT CLEARED' : 'INFEASIBLE'}</span></td>
              </tr>;
            })}
          </tbody></table></div>
          <div className="sc-policy-note"><ShieldCheck size={16} /><div><strong>{result.assumptions.decision_policy}</strong><p>{result.assumptions.risk_warning}</p></div></div>
        </section>

        {(result.decision_sensitivity?.available || result.cash_reserve_sensitivity?.available) && <section className="sc-panel sc-tipping-panel">
          <SectionTitle number="05" icon={Target} title="Decision tipping points" detail="Change lead time or starting cash to see where the plan crosses a configured confidence-bound risk threshold." />
          {result.decision_sensitivity?.available && <>
            <div className="sc-tipping-highlight"><div><small>MAX ALTERNATE LEAD TIME PASSING SLA LOWER-BOUND GUARDRAIL</small><strong>{result.decision_sensitivity.maximum_lead_time_meeting_sla_guardrail == null ? 'No tested value' : `${result.decision_sensitivity.maximum_lead_time_meeting_sla_guardrail} days`}</strong><p>{result.decision_sensitivity.note}</p></div><div className="sc-tipping-icon"><TrendingUp size={24} /></div></div>
            <div className="sc-tipping-bars">{(result.decision_sensitivity.tested_lead_times || []).map((point) => {
              const width = Math.max(0, Math.min(100, Number(point.sla_success_probability || 0)));
              return <div className="sc-tipping-row" key={point.lead_time_days}><span>{point.lead_time_days}d</span><div className="sc-tipping-track"><div className={`sc-tipping-fill ${point.passes_sla_guardrail ? 'is-pass' : 'is-fail'}`} style={{ width: `${width}%` }} /></div><strong>{pct(point.sla_success_probability)}</strong><small>{point.passes_sla_guardrail ? 'PASS' : 'FAIL'}</small></div>;
            })}</div>
          </>}
          {result.cash_reserve_sensitivity?.available && <div className="sc-cash-threshold">
            <div className="sc-cash-threshold-top"><div><span className="sc-kicker">CASH RESERVE THRESHOLD</span><h3>{money(result.cash_reserve_sensitivity.minimum_starting_cash_estimate, 2)}</h3><p>Estimated minimum starting cash for the primary supplier's direct-purchase plan to meet the configured non-negative-ending-cash lower-bound guardrail.</p></div><div className="sc-tipping-icon"><Wallet size={23} /></div></div>
            <div className="sc-cash-threshold-metrics"><div><span>Upfront procurement outflow</span><strong>{money(result.cash_reserve_sensitivity.primary_procurement_outflow, 2)}</strong></div><div><span>Cash-risk lower bound at threshold</span><strong>{pct(result.cash_reserve_sensitivity.nonnegative_cash_ci95?.lower)}</strong></div><div><span>Delivery guardrail at this cash level</span><strong>{result.cash_reserve_sensitivity.delivery_guardrail_passes_at_threshold ? 'Also passes' : 'Still unresolved'}</strong></div></div>
            <p className="sc-cash-threshold-note">{result.cash_reserve_sensitivity.method} Runs per check: {result.cash_reserve_sensitivity.runs_per_check}. Delivery risk is evaluated separately; additional cash does not fix an excessively long lead time.</p>
          </div>}
        </section>}

        <section className="sc-panel sc-assumptions-panel">
          <button className="sc-assumptions-toggle" onClick={() => setExpandedAssumptions((value) => !value)} aria-expanded={expandedAssumptions}><div><span className="sc-section-number">06</span><div><h3>Assumptions, provenance and auditability</h3><p>Inspect the exact rules the engine used.</p></div></div><ChevronDown className={expandedAssumptions ? 'is-rotated' : ''} size={18} /></button>
          {expandedAssumptions && <div className="sc-assumptions-content"><div className="sc-integration-grid">
            {Object.entries(result.integrations || {}).map(([key, integration]) => <div key={key} className="sc-integration-card"><span>{key.replaceAll('_', ' ')}</span><StatusTag status={integration?.status}>{integration?.status || 'available'}</StatusTag><small>{integration?.provider || integration?.model || 'Runtime service status'}</small></div>)}
          </div><div className="sc-assumptions-table">{Object.entries(result.assumptions || {}).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{typeof value === 'string' ? value : JSON.stringify(value)}</strong></div>)}</div></div>}
        </section>

        <section className="sc-approval-panel"><div><div className="sc-approval-icon"><CheckCircle2 size={20} /></div><div><strong>Replay the selected action in the audit sandbox</strong><p>This records a fixed-seed simulated outcome only. No supplier is contacted, no customer is contacted and no real order is placed.</p></div></div><button className="sc-button sc-button-secondary" onClick={replayApproval} disabled={!!busy || !!audit}>{busy === 'replay' ? <LoaderCircle className="sc-spin" size={15} /> : <Play size={15} />}{audit ? 'Simulation recorded' : 'Record simulated approval'}</button></section>
        {audit && <section className="sc-panel sc-audit-panel"><div className="sc-panel-heading-inline"><CheckCircle2 size={17} /><div><h3>Audit trail recorded</h3><p>{audit.note}</p></div></div><div className="sc-audit-list">{(audit.audit_log || []).map((line, index) => <div key={`${index}-${line}`}><span>{String(index + 1).padStart(2, '0')}</span><p>{line}</p></div>)}</div></section>}
      </>}

      <footer className="sc-footer"><div className="sc-footer-brand"><Layers3 size={16} /> DIGITAL SHADOW <span>·</span> EVIDENCE-GROUNDED DECISION SIMULATION</div><div><span>NEBIUS TOKEN FACTORY + NVIDIA NEMOTRON</span><i /> <span>TAVILY SEARCH + EXTRACT</span></div><p>Simulation estimates are conditional on stated assumptions. They are not guaranteed forecasts, professional financial advice or evidence about a supplier unless directly sourced. No real transactions occur.</p></footer>
    </div>
  </main>;
}

function GitCompareIcon(props) { return <ArrowUpRight {...props} />; }
