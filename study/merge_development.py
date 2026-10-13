"""Complete development tables without refitting previously saved candidates."""
from pathlib import Path
import json
import hashlib
import pandas as pd
import numpy as np
from run_full_experiment import derive_comparisons

ROOT=Path(__file__).resolve().parent
KEY=['dataset','period','O','L']
def read(path):return pd.read_csv(path,float_precision='round_trip')
def main():
    prior=ROOT/'development_reference/expansion';base=ROOT/'baseline_results';out=ROOT/'development_results'
    out.mkdir(exist_ok=False)
    manifest=json.loads((base/'run_manifest.json').read_text())
    assert manifest['new_model_fits']==24 and manifest['reserved_windows_scored'] is False
    for name in ['inner_candidate_metrics.csv','future_candidate_metrics.csv','selected_procedure_metrics.csv','fit_ledger.csv']:
        first=read(prior/name);second=read(base/name)
        if name=='fit_ledger.csv':
            first['execution_stage']='bounded_recovery';second['execution_stage']='baseline_completion'
            first['execution_fit_id']=first.fit_id;second['execution_fit_id']=second.fit_id
            second['fit_id']=second.fit_id+360
        combined=pd.concat([first,second],ignore_index=True,sort=False)
        combined.to_csv(out/name,index=False)
        assert not combined.duplicated(KEY+(['strategy','model'] if name=='inner_candidate_metrics.csv' else ['strategy'] if name=='selected_procedure_metrics.csv' else ['fit_id'] if name=='fit_ledger.csv' else ['model'])).any()
    cases=read(prior/'case_audit.csv');cases=cases[cases.status=='feasible']
    cases=pd.concat([cases,read(base/'case_audit.csv')],ignore_index=True)
    assert len(cases)==16 and (cases.status=='feasible').all();cases.to_csv(out/'case_audit.csv',index=False)
    locks=json.loads((prior/'locked_choices.json').read_text())+json.loads((base/'locked_choices.json').read_text())
    assert len(locks)==112;(out/'locked_choices.json').write_text(json.dumps(locks,indent=2)+'\n')
    diff,contrast=derive_comparisons(read(out/'selected_procedure_metrics.csv'))
    diff.to_csv(out/'selection_differences.csv',index=False);contrast.to_csv(out/'primary_and_secondary_contrasts.csv',index=False)
    old_primary=read(prior/'primary_and_secondary_contrasts.csv').set_index(['dataset','period','seed']).primary_C
    np.testing.assert_array_equal(contrast.set_index(['dataset','period','seed']).primary_C.sort_index(),old_primary.sort_index())
    earlier=read(ROOT/'development_reference/earlier/primary_and_secondary_contrasts.csv')
    all_contrasts=pd.concat([earlier.assign(stage='earlier sources'),contrast.assign(stage='source extension')],ignore_index=True)
    all_contrasts.to_csv(out/'all_source_period_contrasts.csv',index=False)
    summaries=[]
    for (name,period),g in all_contrasts.groupby(['dataset','period'],sort=False):
        summaries.append(dict(dataset=name,period=period,stage=g.stage.iloc[0],seed_n=len(g),primary_C_mean=g.primary_C.mean(),primary_C_min=g.primary_C.min(),primary_C_max=g.primary_C.max()))
    summary=pd.DataFrame(summaries);summary.to_csv(out/'combined_primary_summary.csv',index=False)
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    (out/'COMPLETION_AUDIT.json').write_text(json.dumps(dict(complete_expansion_fits=384,additional_baseline_fits=24,
        previous_completed_fits=360,previous_interrupted_maximum_fits=21,maximum_expansion_attempts=405,
        source_period_units=8,primary_contrasts_unchanged=True,reserved_numeric_targets_parsed=0,output_sha256=files),indent=2)+'\n')
    lines=['| Source | Period | Primary mean | Seed minimum | Seed maximum |','| --- | --- | --- | --- | --- |']
    for r in summary.itertuples():lines.append(f'| {r.dataset} | {r.period} | {r.primary_C_mean:.6f} | {r.primary_C_min:.6f} | {r.primary_C_max:.6f} |')
    report='''# Combined development interpretation, fixed before final scoring

The missing traffic T1 (0,0) case was completed with 24 additional fits and passed 13 independent reconstruction checks. The expansion now has sixteen complete cases and 384 complete fitted-candidate executions. Earlier saved scores were reused unchanged; interrupted in-memory outputs remain excluded. All expansion secondary comparisons are now available, and all four expansion primary contrasts are unchanged. Together with the earlier Bike/Beijing experiment, the development evidence covers four source series and eight related source-period units.

'''+ '\n'.join(lines)+'''

One development unit is positive, four are zero and three are negative. Every random seed selected the same candidate within each unit/setting here, so ranges collapse. Repeated split seeds and adjacent periods are dependent. They do not supply forty independent replications, p-values or confidence intervals.

The narrow claim is that distinguishing physical measurement arrival from additional label-use permission can change model-selection regret in a source- and period-dependent way under a simulated availability contract. These results do not support universal chronological superiority. Most contrasts are zero in this small four-candidate menu, so the selection diagnostic may be insensitive even when candidate forecasting errors change. No claim of statistical equivalence or isolated causal feature-staleness effect is made.

Final evaluation will assess the previously locked T2 inner choices at the later reserved deployment boundary, sharing one candidate refit per setting. It will not choose models based on observed T2 future error or reserved error. This is a test of carried-forward fixed selections, not refreshed split policies or an online adaptive learner. Keep all four final regions uninspected until the exact final plan, choices, code and normalization history rules are frozen. A historical temporal holdout does not make these public benchmarks a formally preregistered or newly collected external cohort. Novelty and publication prospects remain unestablished.
'''
    (ROOT/'DEVELOPMENT_FINDINGS.md').write_text(report)
    print(summary.to_string(index=False))

if __name__=='__main__':main()
