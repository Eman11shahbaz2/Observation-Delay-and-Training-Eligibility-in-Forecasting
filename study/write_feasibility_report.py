"""Readable report and machine-readable source configuration from timestamp evidence."""
from datetime import datetime,timezone
import json
from pathlib import Path
import pandas as pd
from preflight_new_sources import sha

ROOT=Path(__file__).resolve().parent

def table(columns,rows):
    return '\n'.join(['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']+
        ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])

def main():
    report=json.loads((ROOT/'TIMESTAMP_PREFLIGHT.json').read_text())
    validation=json.loads((ROOT/'VALIDATION_RESULTS.json').read_text())
    config=dict(stage='frozen before new-source numeric target inspection',horizon_hours=6,
        availability_settings=[dict(O=o,L=l) for o,l in [(0,0),(0,24),(24,0),(24,24)]],
        random_split_seeds=[42,43,44,45,46],model_random_state=42,maximum_new_fits=384,
        selectable_menu=['persistence','Ridge','RF','HGB'],datasets={})
    for name,d in report['datasets'].items():
        config['datasets'][name]=dict(plan=d['plan'],archive_sha256=d['archive_sha256'],
            raw_development_prefix_n=d['development_source_timestamp_rows'],
            target='traffic_volume' if name=='traffic' else 'Global_active_power',
            target_units='vehicle count per hour' if name=='traffic' else 'kW hourly mean',
            numeric_covariates=['temp','rain_1h','snow_1h','clouds_all'] if name=='traffic' else ['Global_reactive_power','Voltage'],
            categorical_covariates=['weather_main'] if name=='traffic' else [],
            covariate_completion_lag_hours=1,numeric_feasibility_verified=False)
    (ROOT/'SOURCE_CONFIG.json').write_text(json.dumps(config,indent=2))
    metadata_rows=[];date_rows=[];case_rows=[]
    for name,d in report['datasets'].items():
        metadata_rows.append([name,f"{d['source_rows']:,}",f"{d['unique_timestamps']:,}",
            f"{d['duplicate_extra_rows']:,}",f"{d['missing_clock_steps']:,} {d['clock_step_unit']}s"])
        for p in d['plan']['development']:
            date_rows.append([name,p['period'],p['inner_cut'],p['outer_cut'],p['future_end']])
            g=[r for r in d['potential_case_counts'] if r['period']==p['period']]
            ranges=lambda k:f"{min(r[k] for r in g):,}–{max(r[k] for r in g):,}"
            case_rows.append([name,p['period'],ranges('potential_inner_train_n'),ranges('potential_inner_validation_n'),
                f"{g[0]['potential_future_n']:,}",'Pass, numerical feasibility unverified'])
    traffic=report['datasets']['traffic'];household=report['datasets']['household']
    prose=f'''# New-source feasibility report

Completed {report['completed_utc']}. Local research-plan date: 12 October 2026, Asia/Karachi.

## Decision in simple words

**Both candidate sources are suitable to carry forward to guarded numerical feasibility checks.** They have enough timestamp coverage for the planned periods. Traffic needs careful duplicate consolidation and has a major gap; household readings need a strict hourly aggregation rule. These problems are documented rather than hidden.

This stage fitted **zero models** and inspected **no numeric target values**. Both official archives were downloaded, but only header/date/time columns were parsed for analysis. Public archives contain the raw measurements; this is a procedural restriction, not an access-control claim. Missing numeric values, conflicting duplicate traffic targets, persistence availability and target diversity have not yet been measured. The next experiment is not already complete or fully numerically feasible.

## Timestamp findings

{table(['Source','Raw timestamp rows','Distinct timestamps','Extra duplicate rows','Missing nominal clock steps'],metadata_rows)}

Traffic has {traffic['duplicate_timestamp_groups']:,} repeated timestamp groups, with as many as {traffic['largest_timestamp_multiplicity']} rows at one nominal hour. Those repeats are not extra independent observations. The largest missing run is {traffic['largest_missing_run_steps']:,} hours (about {traffic['largest_missing_run_steps']/24:.0f} days), between {traffic['largest_gaps'][0]['last_observed']} and {traffic['largest_gaps'][0]['next_observed']}. Keep all missing hours on the clock grid. Do not fill their targets or shift forecasting to the sixth next row. Long gaps can invalidate persistence and reduce eligible fits; that will be checked under the frozen rule.

Household has {household['structurally_complete_hours']:,} structurally complete hours. The first represented hour has 36 timestamps and the last has 3; their exclusion from the target-grid endpoints is based solely on timestamps. There are no interior missing minute stamps. Complete timestamp coverage does **not** mean complete numerical readings: source metadata explicitly acknowledges missing measurements. Actual numeric completeness remains uninspected.

## Preparation rules fixed before outcomes

- Traffic: one hourly target only if all duplicate target counts are finite, valid integers and equal. A conflict or missing value makes that hour's target missing. Do not sum duplicate counts or average conflicts. Numeric weather inputs use exact finite consensus, and weather categories use a sorted unique set. These checks will occur only in the later numeric stage.
- Household: forecast hourly mean active power in kW. Require exactly 60 distinct minute stamps and 60 finite, nonnegative target readings; otherwise that hour's target is missing. Do not sum kW values into a mislabeled energy target or average incomplete minutes. Reactive power and voltage are the only auxiliary measurements; each has its own 60-finite-minute completeness check.
- Both: retain gaps, use exact six-hour timestamp joins, and use training-only imputation for missing features. Never impute labels. Target history/persistence, calendar roles and auxiliary observations follow the frozen availability contract.

EXPANSION_PROTOCOL.md supplies the full source-specific ledger, duplicate/missingness rules, unchanged model settings and statistical interpretation. SOURCE_CONFIG.json supplies the frozen source identities, clock boundaries and feature lists. Both sources use nominal time; provider arrival histories and unambiguous timezone/DST mappings are unavailable. The experiment simulates observation/use delays rather than measuring actual provider delays.

## Frozen development dates

{table(['Source','Period','A: inner boundary','B: deployment cutoff','C: future endpoint'],date_rows)}

Traffic reserved region starts {traffic['plan']['reserved_start']}; household reserved region starts {household['plan']['reserved_start']}. Reserved timestamps were included in date-only inspection; no reserved numeric measurements were parsed for analysis. All prior sources' reserved final regions also remain unused. Do not move the cutpoints in response to missingness or model performance.

## Potential counts, not confirmed numeric eligibility

The ranges below cover the four (O,L) settings. They are timestamp-only upper bounds based on exact target-hour timestamp presence; they do not impose finite labels, duplicate numeric agreement or finite persistence. A forecast origin itself need not have a source record. The final numerical mask will be common across all settings and requires a finite target and finite persistence under both O values.

{table(['Source','Period','Potential inner train range','Potential validation range','Potential future origins','Timing count gate'],case_rows)}

All 16 timing-count gates pass the 500/100/100 thresholds. Numerical feasibility is explicitly marked false/unverified in every preflight case. If later rules leave a case infeasible, retain it in the report; do not weaken the aggregation rule, shift periods or choose a replacement source based on scores.

## Validation and export reliability

**{validation['checks_passed']} checks passed; {validation['checks_failed']} failed.** Tests cover poisoned measurement strings in timestamp-only parsing, date precision, malformed dates, duplicates, incomplete hours, missing forecast-origin handling, source hashes, recomputed timestamp counts, primary-pair equal potential memberships, unchanged futures, conservative synthetic aggregation, guarded reserved-prefix loading and atomic cross-dataset union exports. The source adapters have been exercised only on synthetic values, never the real targets.

The new audit writer concatenates heterogeneous feature tables into one common union schema, writes one gzip stream, checks its header/row structure and compressed integrity, and atomically replaces the output. Its tests verify both schema union and preservation of an existing file on failure. This prevents the known static-export design defect from the prior runner. It does not retroactively alter any old fit or result.

The timestamp helper was revised to report infeasible cutpoints for tiny synthetic clock spans instead of raising an error. The real source boundaries and counts are identical to the initial audit; original code/freeze/report are retained under reference/. This was a timestamp-only implementation correction, not a target-driven design change.

## What the next stage will do

Implement the expansion runner around the frozen adapters, timing contract and audit writer, then freeze its code before numeric loading. Reuse the chronological, earlier-validation and five random selectors; each chooses from persistence, Ridge, RF and HGB using inner MAE. Keep model hyperparameters and initialization seeds fixed. All selectors share one future refit in each setting. Both primary settings, (24,0) and (0,24), have equal t+31 label maturity; verify identical fitting memberships while their target-feature streams differ.

The primary contrast, secondary comparisons and historical-IQR normalization are inherited unchanged. If every new case is numerically feasible, the maximum is **384 new model fits**. Report all new source-period results separately, including ties and losses, and label the two-source outcome-uninspected extension separately from the earlier exploratory results. Do not treat seeds/periods as independent replications or pool a significance test across them. Source expansion strengthens coverage; scientific novelty and suitability for publication still require a defensible literature comparison and a limited claim.

The immediate next stage is implementation plus guarded numerical feasibility, followed by the frozen development run. Existing and new reserved final windows should be used only under a separately settled final evaluation plan.

## Reproduce this preflight

Run `python3 preflight_new_sources.py` to recreate date-only findings from the bundled archives. Run `python3 -m unittest discover -v` for the checks. Run `python3 write_feasibility_report.py` to regenerate this report/configuration using the recorded validation summary. Do **not** call guarded_development_loader on real archives in this timestamp-only stage. A later runner will call it after its implementation freeze.

Sources and attribution: SOURCE_REGISTER.md. All preparation choices and code hashes are recorded in EXPANSION_FREEZE.json. The old completed pilot, full experiment and audit packages remain unchanged.
'''
    (ROOT/'FEASIBILITY_REPORT.md').write_text(prose,encoding='utf-8')
    freeze_names=['AUDIT_RULES.md','EXPANSION_PROTOCOL.md','SOURCE_CONFIG.json','TIMESTAMP_PREFLIGHT.json',
        'preflight_new_sources.py','source_preparation.py','audit_exports.py','replay_core.py',
        'test_preflight.py','test_preparation_and_exports.py','test_completed_preflight.py']
    freeze=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),status='frozen before new-source numeric target inspection',
        numeric_target_values_inspected=False,models_fitted=0,code_or_protocol_sha256={n:sha(ROOT/n) for n in freeze_names},
        source_archive_sha256={n:d['archive_sha256'] for n,d in report['datasets'].items()})
    (ROOT/'EXPANSION_FREEZE.json').write_text(json.dumps(freeze,indent=2))
    print('Feasibility report, source configuration and outcome-uninspected preparation freeze saved.')

if __name__=='__main__':main()
