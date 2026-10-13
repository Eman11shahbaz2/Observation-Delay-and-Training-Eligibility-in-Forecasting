"""Lock the exact choices and protocol before releasing any final measurements."""
from datetime import datetime,timezone
import json
from pathlib import Path
import study_api as f

ROOT=Path(__file__).resolve().parent
def main():
    if (ROOT/'FINAL_FREEZE.json').exists():raise ValueError('Final plan is already frozen.')
    validation=json.loads((ROOT/'BASELINE_VALIDATION.json').read_text())
    assert validation['checks_passed']==13 and validation['checks_failed']==0
    completion=json.loads((ROOT/'development_results/COMPLETION_AUDIT.json').read_text())
    assert completion['complete_expansion_fits']==384 and completion['reserved_numeric_targets_parsed']==0
    choices=[]
    for label in ['earlier','expansion']:
        records=json.loads((ROOT/f'development_reference/{label}/locked_choices.json').read_text())
        for row in records:
            if row['period']!='T2':continue
            scores=row['inner_mae_all_candidates']
            winner=min(f.MODELS,key=lambda model:(scores[model],f.MODELS.index(model)))
            assert row['selected_model']==winner
            choices.append(dict(**row,development_locked_utc=row['locked_utc']))
    assert len(choices)==112
    assert len({(r['dataset'],r['O'],r['L'],r['strategy']) for r in choices})==112
    locked=datetime.now(timezone.utc).isoformat()
    (ROOT/'FINAL_CHOICES.json').write_text(json.dumps(dict(locked_utc=locked,selection_refresh=False,source_period='T2',choices=choices),indent=2)+'\n')
    datasets={name:{k:f.source_metadata(name)['plan'][k] for k in ['start','reserved_start','reserved_end_exclusive']} for name in f.NAMES}
    plan=dict(created_utc=locked,horizon_hours=6,settings=[[0,0],[0,24],[24,0],[24,24]],seeds=[42,43,44,45,46],
        datasets=datasets,maximum_final_fits=48,minimum_train=500,minimum_future=100,normalization_max_maturity_hours=55,
        selections_from='unchanged T2 inner-only scores',selection_refresh_fits=0,final_evaluation_repetitions=1)
    (ROOT/'FINAL_PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
    files=['FINAL_PROTOCOL.md','FINAL_PLAN.json','FINAL_CHOICES.json','DEVELOPMENT_FINDINGS.md','BASELINE_VALIDATION.json',
        'study_api.py','run_final_evaluation.py','forecast_pilot.py','replay_core.py','metadata_preflight.py','source_preparation.py',
        'expansion_api.py','audit_exports.py','run_full_experiment.py','freeze_final.py','test_final_design.py','METADATA_PREFLIGHT.json','TIMESTAMP_PREFLIGHT.json',
        'development_results/COMPLETION_AUDIT.json','development_results/combined_primary_summary.csv',
        'development_reference/earlier/locked_choices.json','development_reference/expansion/locked_choices.json']
    files += [f'source_archives/{name}_official.zip' for name in f.NAMES]
    freeze=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),reserved_numeric_targets_inspected_before_freeze=False,
        final_scores_computed_before_freeze=False,sha256={name:f.sha(ROOT/name) for name in files})
    (ROOT/'FINAL_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n')
    print('Final protocol and 112 carried-forward choices frozen; reserved measurements remain unparsed.')

if __name__=='__main__':main()
