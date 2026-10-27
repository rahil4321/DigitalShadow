import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, BadgeCheck, BarChart3, CalendarClock, CheckCircle2,
  ChevronRight, Clock3, Database, ExternalLink, FileText, Gauge, GitCompare,
  Globe2, Info, Layers3, Play, RefreshCw, ShieldAlert, ShieldCheck,
  SlidersHorizontal, Sparkles, Wallet, Zap,
} from 'lucide-react';
import { apiFetch } from './apiClient.js';
import './App.css';
import ScenarioStudio from './ScenarioStudio.jsx';

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\/+$/, '');
const RUN_OPTIONS = [100, 200, 300, 500, 750, 1000];

// Prevent an unexpected render-time error from leaving the entire page blank.
class RenderErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Digital Shadow UI rendering error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: '#080d12', color: '#e8f0f5', fontFamily: 'Inter, system-ui, sans-serif' }}>
          <section style={{ maxWidth: 560, padding: 28, border: '1px solid #31414d', borderRadius: 16, background: '#101820' }} role="alert">
            <p style={{ color: '#86efac', letterSpacing: '0.12em', fontSize: 12, fontWeight: 700 }}>DIGITAL SHADOW / UI RECOVERY</p>
            <h1 style={{ marginBottom: 8 }}>This view encountered a rendering error.</h1>
            <p style={{ color: '#b8c6d1', lineHeight: 1.6 }}>Your simulation request may have succeeded, but the results could not be displayed. Refresh the page to recover; check the browser console if the issue repeats.</p>
            <button onClick={() => window.location.reload()} style={{ marginTop: 12, padding: '10px 16px', border: 0, borderRadius: 8, background: '#a3e635', color: '#17210b', fontWeight: 700, cursor: 'pointer' }}>Reload Digital Shadow</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function money(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(Number(value));
}

function pct(value) {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : `${Number(value).toFixed(1)}%`;
}

function ciRange(interval, formatter = pct) {
  if (!interval || !Number.isFinite(Number(interval.lower)) || !Number.isFinite(Number(interval.upper))) return 'not available';
  return `${formatter(interval.lower)}–${formatter(interval.upper)}`;
}

function safeWebUrl(value) {
  if (!value || typeof value !== 'string') return '';
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && url.hostname && !url.username && !url.password ? url.href : '';
  } catch {
    return '';
  }
}

function relativePoints(values, cx = 130, cy = 105, radius = 72) {
  return values.map((value, index) => {
    const angle = (-90 + index * 120) * Math.PI / 180;
    const r = radius * Math.max(0, Math.min(100, Number(value) || 0)) / 100;
    return `${(cx + Math.cos(angle) * r).toFixed(1)},${(cy + Math.sin(angle) * r).toFixed(1)}`;
  }).join(' ');
}

export default function App() {
  const [activeView, setActiveView] = useState('studio');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isDisrupted, setIsDisrupted] = useState(false);
  const [numRuns, setNumRuns] = useState(1000);
  const [executing, setExecuting] = useState(false);
  const [audit, setAudit] = useState(null);
  const [auditVisible, setAuditVisible] = useState(true);
  const [error, setError] = useState('');

  const fetchSimulation = useCallback(async (disruption = false, runs = 1000) => {
    setLoading(true);
    setError('');
    setAudit(null);
    setAuditVisible(true);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/simulate?disruption=${disruption}&num_runs=${runs}`,
      );
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Simulation request failed (${response.status}).`);
      if (!body.simulation_id || !body.best_strategy_data || !Array.isArray(body.strategies)) {
        throw new Error('The backend returned an incomplete simulation payload.');
      }
      setData(body);
      setIsDisrupted(disruption);
      setNumRuns(runs);
    } catch (e) {
      setError(`${e.message} Confirm that the FastAPI backend is running on ${API_BASE_URL}.`);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeView === 'demo' && !data) fetchSimulation(false, 1000);
  }, [activeView, data, fetchSimulation]); // Load the classic demo only when opened.

  const approveStrategy = useCallback(async () => {
    if (!data?.simulation_id || !data?.best_strategy_data?.strategy_id) return;
    setExecuting(true);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          simulation_id: data.simulation_id,
          strategy_id: data.best_strategy_data.strategy_id,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || `Approval failed (${response.status}).`);
      setAudit(body);
      setAuditVisible(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setExecuting(false);
    }
  }, [data]);

  const best = data?.best_strategy_data;
  const feasibleStrategies = useMemo(
    () => (data?.strategies || []).filter((item) => item.feasible),
    [data],
  );
  const sourceCount = data?.reality?.sources?.filter((source) => safeWebUrl(source.url)).length || 0;
  const sourceCoverage = Math.round(Math.min(sourceCount, 3) / 3 * 100);
  const strategyCoverage = Math.round(Math.min(feasibleStrategies.length, 3) / 3 * 100);

  if (activeView === 'studio') {
    return <RenderErrorBoundary><ScenarioStudio onOpenDemo={() => setActiveView('demo')} /></RenderErrorBoundary>;
  }

  if (loading || executing) {
    return (
      <main className="ds-loading-screen">
        <div className="ds-loading-orbit"><Activity size={27} /></div>
        <p className="ds-eyebrow">DIGITAL SHADOW / DECISION ENGINE</p>
        <h1>{executing ? 'Replaying approved decision' : 'Simulating alternate futures'}</h1>
        <p className="ds-muted">{executing
          ? 'Restoring saved assumptions and running one seeded simulated outcome.'
          : `Evaluating ${numRuns.toLocaleString()} scenarios per strategy.`}</p>
      </main>
    );
  }

  if (!data || !best) {
    return (
      <main className="ds-error-shell">
        <div className="ds-error-card">
          <div className="ds-brand-mark"><Layers3 size={24} /></div>
          <p className="ds-eyebrow">DIGITAL SHADOW</p>
          <h1>Simulation unavailable</h1>
          <p>{error || 'The service did not return a usable recommendation.'}</p>
          <button className="ds-button ds-button-primary" onClick={() => fetchSimulation(isDisrupted, numRuns)}>
            <RefreshCw size={16} /> Retry simulation
          </button>
        </div>
      </main>
    );
  }

  const strategyProfits = feasibleStrategies.map((s) => Number(s.expected_profit || 0));
  const maxProfit = Math.max(0, ...strategyProfits);
  const maxAbsProfit = Math.max(1, ...strategyProfits.map((value) => Math.abs(value)));
  const slaGuardrailBound = Number(best.sla_success_ci95?.lower ?? best.sla_success_probability ?? 0);
  const cashGuardrailBound = Number(best.solvency_ci95?.lower ?? best.solvency_probability ?? 0);
  const riskProfile = slaGuardrailBound >= 90 && cashGuardrailBound >= 95
    ? { label: 'Controlled', color: 'teal', icon: ShieldCheck, detail: 'High modelled deadline success and non-negative ending cash in the sampled runs.' }
    : (slaGuardrailBound < 60 || cashGuardrailBound < 80)
      ? { label: 'High', color: 'rose', icon: AlertTriangle, detail: 'The sampled futures show material delivery and/or negative-ending-cash risk.' }
      : { label: 'Elevated', color: 'amber', icon: ShieldAlert, detail: 'The recommendation has meaningful delivery or non-negative-cash uncertainty.' };
  const RiskIcon = riskProfile.icon;
  const radarValues = [
    Number(best.sla_success_probability || 0),
    Number(best.solvency_probability || 0),
    maxProfit > 0 ? Math.max(0, Math.min(100, Number(best.expected_profit || 0) / maxProfit * 100)) : 0,
  ];

  return (
    <main className="ds-shell">
      <div className="ds-app-frame">
        <header className="ds-header">
          <div className="ds-brand-lockup">
            <div className="ds-brand-mark"><Layers3 size={23} strokeWidth={1.8} /></div>
            <div>
              <p className="ds-eyebrow">OPERATIONAL DECISION INTELLIGENCE</p>
              <h1>DIGITAL <span>SHADOW</span></h1>
            </div>
          </div>
          <div className="ds-header-right">
            <button className="ds-text-button" style={{ marginTop: 0, marginRight: 8 }} onClick={() => setActiveView('studio')}>Open Scenario Studio ↗</button>
            <span className="ds-live-dot" />
            <span className="ds-header-status">SIMULATION MODE</span>
            <span className="ds-header-separator" />
            <span className="ds-run-id">RUN {data.simulation_id.slice(0, 8).toUpperCase()}</span>
          </div>
        </header>

        {error && <div className="ds-inline-error"><AlertTriangle size={17} />{error}</div>}
        {sourceCount === 0 && <div className="ds-inline-warning" role="status" aria-live="polite">
          <AlertTriangle size={17} />
          <span><strong>External evidence is unavailable for this run.</strong> The slow-supplier lead time is a demo stress assumption, not a live source-backed estimate. Nebius inference status is shown separately below.</span>
        </div>}
        {sourceCount > 0 && data.reality.provenance !== 'web_estimate' && <div className="ds-inline-warning" role="status" aria-live="polite">
          <AlertTriangle size={17} />
          <span><strong>Sources retrieved; live delay estimate unavailable.</strong> The application is retaining source links but using its labelled stress assumption.</span>
        </div>}

        <section className="ds-control-summary ds-panel">
          <aside className="ds-control-column">
            <div className="ds-section-heading">
              <div className="ds-heading-icon"><SlidersHorizontal size={17} /></div>
              <div><h2>Simulation controls</h2><p>Set the scenario, then compare futures.</p></div>
            </div>

            <div className="ds-control-block">
              <div className="ds-control-label-row">
                <label htmlFor="run-count">Monte Carlo sample</label>
                <span className="ds-value-chip">{numRuns} runs</span>
              </div>
              <select id="run-count" className="ds-select" value={numRuns}
                onChange={(event) => setNumRuns(Number(event.target.value))}>
                {RUN_OPTIONS.map((runs) => <option key={runs} value={runs}>{runs} scenarios per strategy</option>)}
              </select>
              <p className="ds-control-hint">More runs can stabilize the estimate, but do not guarantee accuracy.</p>
            </div>

            <div className="ds-control-block ds-scenario-card">
              <div className="ds-control-label-row">
                <span className="ds-field-label">Operating scenario</span>
                <span className={`ds-status-pill ${isDisrupted ? 'is-warning' : 'is-neutral'}`}>
                  {isDisrupted ? 'Budget shock' : 'Baseline'}
                </span>
              </div>
              <div className="ds-scenario-description">
                <span className={`ds-scenario-icon ${isDisrupted ? 'is-warning' : ''}`}>
                  {isDisrupted ? <Zap size={17} /> : <ShieldCheck size={17} />}
                </span>
                <div><strong>{isDisrupted ? 'Credit line frozen' : 'Normal cash position'}</strong>
                  <span>{isDisrupted ? `Available cash is $4,000. Recovery models a $${Number(data.assumptions.customer_deposit_amount).toLocaleString()} customer advance with ${Math.round(data.assumptions.customer_deposit_acceptance_probability * 100)}% acceptance probability; both are hypothetical assumptions.` : 'Starting cash is $10,000.'}</span></div>
              </div>
            </div>

            <button className="ds-button ds-button-light" onClick={() => fetchSimulation(!isDisrupted, numRuns)}>
              {isDisrupted ? <RefreshCw size={16} /> : <Zap size={16} />}
              {isDisrupted ? 'Reset to baseline' : 'Inject budget crisis'}
            </button>
            <button className="ds-button ds-button-quiet" onClick={() => fetchSimulation(isDisrupted, numRuns)}>
              <Play size={15} /> Run full simulation <ChevronRight size={15} />
            </button>
            <div className="ds-control-footnote"><Info size={13} /> Scenario changes are hypothetical and stay inside the simulator.</div>
          </aside>

          <div className="ds-metric-column">
            <div className="ds-metric-grid">
              <MetricCard label="EXPECTED OPERATING PROFIT" value={money(best.expected_profit, 2)}
                icon={<BarChart3 size={16} />} tone={Number(best.expected_profit) >= 0 ? 'teal' : 'rose'}
                note={`Across ${best.runs} sampled futures`} />
              <MetricCard label="RISK PROFILE" value={riskProfile.label}
                icon={<RiskIcon size={16} />} tone={riskProfile.color} note={riskProfile.detail} />
              <MetricCard label="EXPECTED FINAL CASH" value={money(best.cash, 2)}
                icon={<Wallet size={16} />} tone="neutral"
                note={`5th percentile: ${money(best.p05_cash, 2)} · Worst observed: ${money(best.worst_case_cash, 2)}`} />
              <MetricCard label="SLA SUCCESS PROBABILITY" value={pct(best.sla_success_probability)}
                icon={<CalendarClock size={16} />} tone={slaGuardrailBound >= 80 ? 'teal' : 'amber'}
                note={`95% Wilson interval: ${ciRange(best.sla_success_ci95)} · empirical, not a guarantee`} />
            </div>
            <div className="ds-recommended-strip">
              <div className="ds-recommended-icon"><BadgeCheck size={19} /></div>
              <div className="ds-recommended-copy"><span>RECOMMENDED STRATEGY</span><strong>{best.name}</strong></div>
              <div className="ds-recommended-meta"><span>Cash guardrail · 95% lower bound</span><strong>{pct(cashGuardrailBound)}</strong></div>
              <div className="ds-recommended-meta"><span>Decision rule</span><strong>Guardrails first</strong></div>
            </div>
          </div>
        </section>

        <section className="ds-analysis-grid">
          <article className="ds-panel ds-panel-padding ds-evidence-panel">
            <div className="ds-panel-title-row">
              <div className="ds-panel-icon"><Gauge size={17} /></div>
              <div><h2>Evidence &amp; model coverage</h2><p>Visible provenance instead of a made-up confidence score.</p></div>
            </div>
            <CoverageBar label="External source coverage" right={`${sourceCount} source${sourceCount === 1 ? '' : 's'}`} value={sourceCoverage} tone="teal" />
            <CoverageBar label="Distinct feasible strategies" right={`${feasibleStrategies.length} of 3`} value={strategyCoverage} tone="purple" />
            <CoverageBar label="Sample size vs. 1,000-run cap" right={`${best.runs} / 1,000`} value={Math.min(100, best.runs / 10)} tone="amber" />
            <div className="ds-provider-status" aria-label="Integration provenance">
              <ProviderStatusRow label="Nemotron planner" status={data.integrations?.planner?.status} model={data.integrations?.planner?.model} />
              <ProviderStatusRow label="Nemotron analyst" status={data.integrations?.analyst?.status} model={data.integrations?.analyst?.model} />
              <ProviderStatusRow label="Tavily evidence" status={data.integrations?.external_evidence?.status || data.reality?.provenance} />
            </div>
            <div className="ds-evidence-footer">
              <span className={`ds-provenance-dot ${data.reality.provenance === 'web_estimate' ? 'is-live' : 'is-demo'}`} />
              <p><strong>{data.reality.provenance === 'web_estimate' ? 'Web-informed estimate' : 'Demo / fallback assumption'}</strong>
                <span>{data.reality.summary}</span></p>
            </div>
          </article>

          <article className="ds-panel ds-panel-padding ds-radar-panel">
            <div className="ds-panel-title-row">
              <div className="ds-panel-icon"><GitCompare size={17} /></div>
              <div><h2>Risk &amp; opportunity radar</h2><p>Normalised metrics for the selected recommendation.</p></div>
            </div>
            <div className="ds-radar-layout">
              <svg className="ds-radar-svg" viewBox="0 0 260 220" role="img" aria-label="Radar chart of SLA success, solvency, and relative profit normalized against the best nonnegative result">
                {[20, 38, 56, 74].map((r) => <polygon key={r} points={relativePoints([100, 100, 100], 130, 105, r)} className="ds-radar-ring" />)}
                <line x1="130" y1="105" x2="130" y2="33" className="ds-radar-axis" />
                <line x1="130" y1="105" x2="192" y2="141" className="ds-radar-axis" />
                <line x1="130" y1="105" x2="68" y2="141" className="ds-radar-axis" />
                <polygon points={relativePoints(radarValues)} className="ds-radar-area" />
                {relativePoints(radarValues).split(' ').map((point, index) => {
                  const [cx, cy] = point.split(',');
                  return <circle key={index} cx={cx} cy={cy} r="4.5" className="ds-radar-point" />;
                })}
              </svg>
              <div className="ds-radar-legend">
                <RadarLegend tone="teal" label="SLA success" value={pct(best.sla_success_probability)} />
                <RadarLegend tone="purple" label="Cash ≥ $0" value={pct(best.solvency_probability)} />
                <RadarLegend tone="amber" label="Profit vs. best candidate" value={maxProfit > 0 ? pct(Math.max(0, Math.min(100, Number(best.expected_profit || 0) / maxProfit * 100))) : 'No positive candidate'} />
                <p className="ds-small-note">Relative profit is scaled against the best candidate in this run; it is not a confidence score.</p>
              </div>
            </div>
          </article>
        </section>

        <section className="ds-panel ds-panel-padding ds-futures-panel">
          <div className="ds-panel-heading-wide">
            <div className="ds-panel-title-row">
              <div className="ds-panel-icon"><GitCompare size={17} /></div>
              <div><h2>Alternate futures</h2><p>Compare the actions and consequences before approving a decision.</p></div>
            </div>
            <div className="ds-heading-badges"><span><Database size={13} /> {data.assumptions.num_runs} runs / strategy</span><span><Clock3 size={13} /> Deadline: Day 4</span></div>
          </div>
          <div className="ds-profit-chart" role="img" aria-label="Diverging bar chart comparing expected operating profit; bars above the center line are positive and bars below are negative.">
            {feasibleStrategies.map((strategy, index) => {
              const value = Number(strategy.expected_profit || 0);
              const height = Math.max(2, 32 * Math.abs(value) / maxAbsProfit);
              const barPosition = value > 0 ? { bottom: '50%' } : value < 0 ? { top: '50%' } : { top: 'calc(50% - 1px)' };
              return <div className={`ds-profit-column tone-${index % 3} ${value < 0 ? 'is-negative' : ''}`} key={strategy.strategy_id}>
                <div className="ds-profit-bar-wrap">
                  <span className="ds-profit-zero-axis" />
                  <div className="ds-profit-bar" style={{ height: `${height}px`, ...barPosition }} />
                </div>
                <strong>{money(value, 0)}</strong>
                <span title={strategy.name}>{strategy.name}</span>
              </div>;
            })}
          </div>
          <div className="ds-strategy-grid">
            {data.strategies.map((strategy) => {
              const recommended = strategy.strategy_id === best.strategy_id;
              return <article key={strategy.strategy_id} className={`ds-strategy-card ${recommended ? 'is-recommended' : ''} ${!strategy.feasible ? 'is-infeasible' : ''}`}>
                {recommended && <div className="ds-card-accent" />}
                <div className="ds-strategy-topline"><span className="ds-strategy-index">{String(data.strategies.indexOf(strategy) + 1).padStart(2, '0')}</span>
                  {recommended && <span className="ds-status-pill is-selected"><CheckCircle2 size={12} /> Recommended</span>}
                  {!strategy.feasible && <span className="ds-status-pill is-warning">Infeasible</span>}
                </div>
                <h3>{strategy.name}</h3>
                <p className="ds-strategy-action">{describeAction(strategy)}</p>
                {!strategy.feasible ? <p className="ds-rejection-copy">{strategy.rejection_reason || 'This action does not satisfy scenario constraints.'}</p> : <>
                  <MetricLine label="Expected operating profit" value={money(strategy.expected_profit, 2)} emphasize={Number(strategy.expected_profit) >= 0} />
                  <MetricLine label="Expected final cash" value={money(strategy.cash, 2)} />
                  <MetricLine label="Expected inventory assets" value={money(strategy.expected_inventory_asset_value, 2)} />
                  <MetricLine label="Net assets after advances" value={money(strategy.expected_net_assets_after_advances, 2)} />
                  <MetricLine label="SLA success · 95% Wilson CI" value={`${pct(strategy.sla_success_probability)} (${ciRange(strategy.sla_success_ci95)})`} />
                  <MetricLine label="Cash ≥ $0 · 95% Wilson CI" value={`${pct(strategy.solvency_probability)} (${ciRange(strategy.solvency_ci95)})`} />
                  <MetricLine label="5th-percentile cash" value={money(strategy.p05_cash, 2)} />
                  <MetricLine label="Worst observed cash" value={money(strategy.worst_case_cash, 2)} />
                </>}
              </article>;
            })}
          </div>
        </section>

        {isDisrupted && data.decision_sensitivity?.available && <section className="ds-panel ds-panel-padding ds-sensitivity-panel">
          <div className="ds-panel-title-row">
            <div className="ds-panel-icon"><Gauge size={17} /></div>
            <div><h2>Decision tipping point</h2><p>How far can the funding assumption weaken before the recovery plan fails the risk guardrails?</p></div>
          </div>
          <div className="ds-sensitivity-grid">
            <div className="ds-sensitivity-metric"><span>Current advance-acceptance assumption</span><strong>{pct(data.decision_sensitivity.current_assumption_probability * 100)}</strong></div>
            <div className="ds-sensitivity-metric"><span>Minimum to pass confidence-bound guardrails</span><strong>{pct(data.decision_sensitivity.minimum_probability * 100)}</strong></div>
            <div className="ds-sensitivity-metric"><span>Modelled buffer above threshold</span><strong>{Number(data.decision_sensitivity.margin_percentage_points).toFixed(1)} pp</strong></div>
          </div>
          <p className="ds-sensitivity-note">At the threshold, the fast-supplier recovery option records {pct(data.decision_sensitivity.threshold_sla_success_probability)} on-time fulfilment; its 95% Wilson lower bound is {pct(data.decision_sensitivity.threshold_sla_success_ci95?.lower)}. This is a deterministic what-if result conditional on the model's illustrative shipment and customer assumptions—not a forecast of real customer behaviour.</p>
        </section>}

        <section className="ds-panel ds-explain-panel">
          <div className="ds-explain-left">
            <div className="ds-panel-title-row"><div className="ds-panel-icon ds-purple-icon"><Sparkles size={18} /></div>
              <div><h2>Explainable decision</h2><p>Why the engine chose this path.</p></div></div>
            <p className="ds-explain-intro">The planner proposes options. Python validates constraints and simulates the business outcomes. The language model may explain the results, but it does not calculate the scores.</p>
            <div className="ds-method-pills"><span>Rule-validated</span><span>Seeded simulation</span><span>Auditable</span></div>
          </div>
          <div className="ds-explain-right">
            <p className="ds-eyebrow">PRIMARY RECOMMENDATION</p>
            <h3>{best.name}</h3>
            <p className="ds-analysis-text">{data.analysis}</p>
            <div className="ds-reason-timeline">
              <ReasonItem icon={<Globe2 size={15} />} title="External signal" detail={`Slow-supplier stress assumption: ${data.initial_state.scenario_slow_supplier_lead_time_days} day(s). ${data.reality.provenance === 'web_estimate' ? 'Informed by general shipping news; not a supplier-specific ETA or forecast.' : 'Demo fallback value; no live source-backed estimate was available.'}`} />
              <ReasonItem icon={<ShieldCheck size={15} />} title="Decision guardrails" detail={data.assumptions.decision_policy} />
              <ReasonItem icon={<BarChart3 size={15} />} title="Outcome evidence" detail={`Expected profit ${money(best.expected_profit, 2)} · SLA success ${pct(best.sla_success_probability)} · 5th-percentile cash ${money(best.p05_cash, 2)}.`} last />
            </div>
            <button className="ds-button ds-button-primary ds-approve-button" disabled={Boolean(audit)} onClick={approveStrategy}>
              {audit ? <CheckCircle2 size={17} /> : <ShieldCheck size={17} />}
              {audit ? 'Simulated decision complete' : `Approve & simulate: ${best.name}`}
              {!audit && <ChevronRight size={17} />}
            </button>
            {audit && !auditVisible && <button className="ds-text-button" onClick={() => setAuditVisible(true)}>View audit trail</button>}
            {audit && auditVisible && <div className="ds-audit-box">
              <div className="ds-audit-heading"><FileText size={17} /><strong>Simulation audit trail</strong><span className="ds-status-pill is-selected">{audit.status}</span></div>
              <p className="ds-audit-note">{audit.note}</p>
              <div className="ds-audit-metric-grid">
                <div><span>Final cash</span><strong>{money(audit.metrics?.final_cash, 2)}</strong></div>
                <div><span>Operating profit</span><strong>{money(audit.metrics?.operating_profit, 2)}</strong></div>
                <div><span>Inventory asset value</span><strong>{money(audit.metrics?.ending_inventory_asset_value, 2)}</strong></div>
                <div><span>Outstanding advances</span><strong>{money(audit.metrics?.outstanding_customer_deposits, 2)}</strong></div>
                <div><span>Net assets after advances</span><strong>{money(audit.metrics?.net_assets_after_customer_advances, 2)}</strong></div>
                <div><span>Single-run SLA</span><strong>{audit.metrics?.sla_met ? 'Met' : 'Missed'} · {pct(audit.metrics?.sla_compliance_pct)}</strong></div>
              </div>
              <div className="ds-audit-lines">{(audit.audit_log || []).map((line, index) => <div key={index}><span>{String(index + 1).padStart(2, '0')}</span>{line}</div>)}</div>
              <button className="ds-text-button" onClick={() => setAuditVisible(false)}>Close audit</button>
            </div>}
          </div>
        </section>

        <section className="ds-panel ds-source-panel">
          <div className="ds-source-heading"><div className="ds-panel-icon"><Globe2 size={17} /></div><div><h2>External intelligence provenance</h2><p>{data.reality.summary}</p></div><span className={`ds-status-pill ${data.reality.provenance === 'web_estimate' ? 'is-live' : 'is-warning'}`}>{data.reality.provenance === 'web_estimate' ? 'Web estimate' : 'Fallback / demo'}</span></div>
          <div className="ds-source-list">
            {(data.reality.sources || []).length ? data.reality.sources.map((source, index) => {
              const sourceUrl = safeWebUrl(source.url);
              return (
              <a key={`${source.url}-${index}`} href={sourceUrl || undefined} target="_blank" rel="noreferrer" className={`ds-source-item ${!sourceUrl ? 'is-disabled' : ''}`}>
                <span className="ds-source-number">{String(index + 1).padStart(2, '0')}</span>
                <span className="ds-source-title">{source.title || 'Untitled source'}</span>
                {sourceUrl && <ExternalLink size={14} />}
              </a>
            );
            }) : <div className="ds-source-empty"><Info size={15} />No source URLs were available. The delay is a demo assumption.</div>}
          </div>
          <div className="ds-source-meta"><span><Clock3 size={13} /> Retrieved: {data.reality.retrieved_at ? new Date(data.reality.retrieved_at).toLocaleString() : 'not available'}</span><span><Info size={13} /> General shipping context is not proof of a specific supplier delay.</span></div>
        </section>

        <footer className="ds-footer"><span>DIGITAL SHADOW · DECISION INTELLIGENCE</span><span><span className="ds-footer-dot" /> Simulated environment · no real-world orders placed</span></footer>
      </div>
    </main>
  );
}

function describeAction(strategy) {
  if (!strategy?.action) {
    return 'No procurement action. Cash is preserved, but the pending order remains exposed to the deadline penalty.';
  }
  const [sku, quantity, supplier] = Array.isArray(strategy.args) ? strategy.args : [];
  if (strategy.action === 'request_customer_deposit_and_order') {
    return `Contingent action: request the scenario-assumed customer advance, then simulate an order for ${quantity} ${sku} from ${supplier} only if accepted.`;
  }
  if (strategy.action === 'place_supplier_order') {
    return `Simulate a purchase order for ${quantity} ${sku} from ${supplier}. No external order is placed.`;
  }
  return 'Unsupported action returned by the backend.';
}

function MetricCard({ label, value, icon, tone = 'neutral', note }) {
  return <div className={`ds-metric-card tone-${tone}`}>
    <div className="ds-metric-label">{label}<span className="ds-metric-icon">{icon}</span></div>
    <div className="ds-metric-value">{value}</div>
    <p>{note}</p>
  </div>;
}

function CoverageBar({ label, right, value, tone }) {
  return <div className="ds-coverage-row">
    <div className="ds-coverage-label"><span>{label}</span><strong>{right}</strong></div>
    <div className="ds-coverage-track"><span className={`tone-${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>
  </div>;
}

function integrationLabel(status) {
  const labels = {
    live_success: 'LIVE INFERENCE',
    live_success_with_fallback: 'LIVE + RULE FALLBACK',
    partial_live_with_fallback: 'PARTIAL LIVE + FALLBACK',
    fallback_missing_key: 'DEMO · KEY MISSING',
    fallback_after_error: 'FALLBACK · PROVIDER ERROR',
    fallback_invalid_output: 'FALLBACK · INVALID OUTPUT',
    web_estimate: 'LIVE SOURCES · SCENARIO ESTIMATE',
    sources_retrieved_estimate_unavailable: 'LIVE SOURCES · DEMO ESTIMATE',
    demo_fallback: 'DEMO · NO LIVE SOURCES',
    test_stub: 'TEST STUB',
  };
  return labels[status] || 'NOT VERIFIED';
}

function integrationTone(status) {
  return ['live_success', 'live_success_with_fallback', 'partial_live_with_fallback', 'web_estimate'].includes(status)
    ? 'is-live' : 'is-warning';
}

function ProviderStatusRow({ label, status, model }) {
  return <div className="ds-provider-row" title={model || undefined}>
    <span>{label}</span>
    <span className={`ds-status-pill ${integrationTone(status)}`}>{integrationLabel(status)}</span>
  </div>;
}

function RadarLegend({ tone, label, value }) {
  return <div className="ds-radar-legend-row"><span className={`ds-legend-dot tone-${tone}`} /><span>{label}</span><strong>{value}</strong></div>;
}

function MetricLine({ label, value, emphasize = false }) {
  return <div className="ds-metric-line"><span>{label}</span><strong className={emphasize ? 'is-positive' : ''}>{value}</strong></div>;
}

function ReasonItem({ icon, title, detail, last = false }) {
  return <div className={`ds-reason-item ${last ? 'is-last' : ''}`}><div className="ds-reason-icon">{icon}</div><div><strong>{title}</strong><p>{detail}</p></div></div>;
}
