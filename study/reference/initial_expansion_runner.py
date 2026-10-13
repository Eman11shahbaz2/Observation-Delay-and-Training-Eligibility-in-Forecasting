"""Frozen 384-fit new-source availability extension; no reserved target analysis."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import platform
import time
import numpy as np
import pandas as pd
import scipy
import sklearn
import expansion_api as f
import replay_core as core
from audit_exports import write_union_csv_gz

ROOT = Path(__file__).resolve().parent
SETTINGS = ((0, 0), (0, 24), (24, 0), (24, 24))
SEEDS = (42, 43, 44, 45, 46)
FITTED = ('Ridge', 'RF', 'HGB')

def utc():
    return datetime.now(timezone.utc).isoformat()

def earlier_split(ordered):
    pool = np.sort(np.concatenate([ordered.train, ordered.validation]))
    n = len(ordered.validation)
    return core.Split(pool[n:], pool[:n], ordered.common_history.copy(), ordered.future.copy())

def selectors(ordered):
    return [('chronological', ordered), ('earlier_validation', earlier_split(ordered))] + [
        (f'random_{seed}', core.matched_random_split(ordered, seed)) for seed in SEEDS]

def worker(model, x, y, train, evaluation):
    start = utc()
    prediction, seconds = f.fit_predict(model, x, y, train, evaluation)
    return prediction, seconds, start, utc()

def derive_comparisons(selection):
    differences = []
    for (name, period, o, l), group in selection.groupby(['dataset', 'period', 'O', 'L'], sort=False):
        g = group.set_index('strategy')
        ch, early = g.loc['chronological'], g.loc['earlier_validation']
        for seed in SEEDS:
            rand = g.loc[f'random_{seed}']
            differences.append(dict(dataset=name, period=period, O=o, L=l, seed=seed,
                chronological_model=ch.selected_model, random_model=rand.selected_model,
                earlier_validation_model=early.selected_model,
                chronological_mae=ch.future_mae, random_mae=rand.future_mae,
                earlier_validation_mae=early.future_mae,
                same_choice=ch.selected_model == rand.selected_model,
                delta_chron_minus_random=ch.normalized_selection_regret-rand.normalized_selection_regret,
                earlier_minus_random=early.normalized_selection_regret-rand.normalized_selection_regret,
                earlier_minus_chron=early.normalized_selection_regret-ch.normalized_selection_regret))
    difference = pd.DataFrame(differences)
    contrasts = []
    if not difference.empty:
        for (name, period, seed), group in difference.groupby(['dataset', 'period', 'seed'], sort=False):
            g = group.set_index(['O', 'L'])
            if not all(setting in g.index for setting in SETTINGS):
                continue
            d00, d024, d240, d2424 = [float(g.loc[s, 'delta_chron_minus_random']) for s in SETTINGS]
            contrasts.append(dict(dataset=name, period=period, seed=seed,
                delta_O0_L0=d00, delta_O0_L24=d024, delta_O24_L0=d240, delta_O24_L24=d2424,
                primary_C=d240-d024, measurement_effect=d240-d00,
                fitting_use_effect=d024-d00, factorial_interaction=(d2424-d240)-(d024-d00)))
    return difference, pd.DataFrame(contrasts)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--output', type=Path, default=ROOT/'results')
    args = parser.parse_args()
    if args.workers < 1: raise ValueError('Positive workers required.')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()): raise ValueError('Output directory must be empty; previous results are preserved.')
    meta = json.loads((ROOT/'TIMESTAMP_PREFLIGHT.json').read_text())
    prior_freeze=json.loads((ROOT/'EXPANSION_FREEZE.json').read_text())
    for name,digest in prior_freeze['code_or_protocol_sha256'].items():
        if f.sha(ROOT/name)!=digest:raise ValueError('Frozen preparation component changed: '+name)
    freeze_files = ['EXPANSION_PROTOCOL.md','SOURCE_CONFIG.json','TIMESTAMP_PREFLIGHT.json',
        'EXPANSION_FREEZE.json','EXECUTION_NOTES.md','source_preparation.py','audit_exports.py',
        'forecast_pilot.py','replay_core.py','availability_contract.py','expansion_api.py',
        'run_full_experiment.py','test_full_design.py','test_expansion_execution.py']
    freeze = dict(frozen_utc=utc(), sha256={name:f.sha(ROOT/name) for name in freeze_files},
        source_archive_sha256={name:info['archive_sha256'] for name,info in meta['datasets'].items()})
    (out/'IMPLEMENTATION_FREEZE.json').write_text(json.dumps(freeze, indent=2))
    manifest = dict(status='running', created_utc=utc(), workers=args.workers,
        expected_maximum_fits=384, new_model_fits=0, cached_model_fits=0,
        reserved_target_rows_loaded=0, reserved_windows_scored=False,
        development_target_values_inspected_after_freeze=True,
        study_status='outcome-uninspected source extension of an exploratory public-data study; not formally preregistered',
        versions=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                      scipy=scipy.__version__, sklearn=sklearn.__version__))
    def save_manifest():
        (out/'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    save_manifest()
    inner, future, selected, locks, cases, ledger, audits = [], [], [], [], [], [], []
    snapshots,maturity,scale_records,prediction_shards,assignment_shards=[],[],[],[],[]
    export_audit={}
    (out/'checkpoints').mkdir()
    count = 0
    run_start = time.perf_counter()
    try:
        # Freeze above precedes the first numeric load. Check every new source before fitting.
        loaded_sources={};numeric_cases=[]
        for name in ('traffic','household'):
            frame,audit=f.load_development(name,meta,ROOT)
            audit['raw_development_diagnostics']=f.profile_raw_development(name,ROOT)
            index=frame.index;y=core.exact_targets(frame[f.CONFIG[name]['target']],index).to_numpy(dtype=float)
            prepared={o:f.build_features(frame,name,o) for o in (0,24)}
            common=np.isfinite(prepared[0][1])&np.isfinite(prepared[24][1]);valid=np.isfinite(y)&common
            audit.update(eligible_origins=int(valid.sum()),missing_exact_targets=int((~np.isfinite(y)).sum()),
                missing_common_persistence=int((~common).sum()))
            audits.append(audit)
            loaded_sources[name]=(frame,y,prepared,valid)
            for period in meta['datasets'][name]['plan']['development']:
                a,b,c=[pd.Timestamp(period[k]) for k in ('inner_cut','outer_cut','future_end')]
                for o,l in SETTINGS:
                    split=core.chronological_split(index,a,b,c,o+l,valid)
                    feasible=(len(split.train)>=500 and len(split.validation)>=100 and len(split.future)>=100 and
                        all(len(np.unique(y[s.train]))>=2 for _,s in selectors(split)))
                    numeric_cases.append(dict(dataset=name,period=period['period'],O=o,L=l,
                        inner_train_n=len(split.train),inner_validation_n=len(split.validation),
                        common_history_n=len(split.common_history),future_n=len(split.future),
                        status='feasible' if feasible else 'infeasible'))
            (out/'dataset_audit.json').write_text(json.dumps(audits,indent=2))
            print(f'Numeric prefix checked: {name}; {int(valid.sum())} eligible origins; reserved values excluded.',flush=True)
        pd.DataFrame(numeric_cases).to_csv(out/'numerical_feasibility.csv',index=False)
        manifest['numerical_feasible_cases']=sum(row['status']=='feasible' for row in numeric_cases)
        manifest['numerical_infeasible_cases']=16-manifest['numerical_feasible_cases'];save_manifest()
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for name in ('traffic', 'household'):
                info = meta['datasets'][name]
                frame,y,prepared,valid=loaded_sources[name]
                index = frame.index
                for o, (x,p,used) in prepared.items():
                    snap = x.reset_index(names='origin')
                    snap.insert(0, 'dataset', name); snap.insert(1, 'O', o)
                    snap['origin_grid_index'] = np.arange(len(index))
                    snap['persistence'] = p; snap['persistence_source_timestamp'] = used
                    snap['eligible_origin'] = valid
                    snapshots.append(snap)
                for o,l in SETTINGS:
                    maturity.append(pd.DataFrame(dict(dataset=name, O=o, L=l,
                        origin_grid_index=np.arange(len(index)), origin=index,
                        target_hour=index+pd.Timedelta(hours=6),
                        physical_target_arrival=index+pd.Timedelta(hours=7+o),
                        label_usable_at=core.label_ready(index,o+l), eligible_origin=valid)))
                for period in info['plan']['development']:
                    label = period['period']
                    a,b,c = [pd.Timestamp(period[k]) for k in ('inner_cut','outer_cut','future_end')]
                    scale_ids = np.flatnonzero(valid & (index<b) & (core.label_ready(index,48)<=b))
                    q = np.quantile(y[scale_ids],[.25,.75]) if len(scale_ids) else [0.,0.]
                    scale = float(q[1]-q[0])
                    scale_records.append(pd.DataFrame(dict(dataset=name, period=label,
                        origin_grid_index=scale_ids, origin=index[scale_ids], y_true=y[scale_ids])))
                    shared_future = None
                    primary_memberships = {}
                    for o,l in SETTINGS:
                        x, persistence, used = prepared[o]
                        ordered = core.chronological_split(index,a,b,c,o+l,valid)
                        designs = selectors(ordered)
                        history, evaluation = ordered.common_history, ordered.future
                        if shared_future is None: shared_future = evaluation
                        elif not np.array_equal(shared_future,evaluation): raise ValueError('Unequal future origins.')
                        primary_memberships[o,l] = [(s.train,s.validation) for _,s in designs]+[(history,evaluation)]
                        if (o,l)==(24,0):
                            for pair1,pair2 in zip(primary_memberships[0,24],primary_memberships[24,0]):
                                if not all(np.array_equal(i,j) for i,j in zip(pair1,pair2)):
                                    raise ValueError('Primary pair memberships differ.')
                        feasible = (len(ordered.train)>=500 and len(ordered.validation)>=100 and
                            len(evaluation)>=100 and all(len(np.unique(y[s.train]))>=2 for _,s in designs))
                        base = dict(dataset=name, period=label, O=o, L=l)
                        cases.append(dict(**base, status='feasible' if feasible else 'infeasible',
                            inner_train_n=len(ordered.train), inner_validation_n=len(ordered.validation),
                            common_history_n=len(history), future_n=len(evaluation), history_iqr=scale,
                            scale_history_n=len(scale_ids), inner_cut=str(a), outer_cut=str(b), future_end=str(c)))
                        pd.DataFrame(cases).to_csv(out/'case_audit.csv',index=False)
                        if not feasible: continue
                        case_predictions, case_assignments, decisions = [], [], []
                        last_inner_end = None
                        jobs_by_design={design:{model:executor.submit(worker,model,x,y,split.train,split.validation)
                            for model in FITTED} for design,split in designs}
                        for design,split in designs:
                            for role,ids in [('train',split.train),('validation',split.validation)]:
                                case_assignments.append(pd.DataFrame(dict(**base, stage='inner', strategy=design,
                                    role=role, origin_grid_index=ids, origin=index[ids])))
                            jobs = jobs_by_design[design]
                            scores = {}
                            for model in f.MODELS:
                                if model=='persistence':
                                    p,seconds = persistence[split.validation],0.
                                else:
                                    p,seconds,start,end = jobs[model].result()
                                    count += 1
                                    ledger.append(dict(**base, stage='inner', strategy=design, model=model,
                                        fit_id=count, train_n=len(split.train), eval_n=len(split.validation),
                                        started_utc=start, completed_utc=end, seconds=seconds, cache_used=False))
                                    last_inner_end = max(last_inner_end or end,end)
                                metrics = f.evaluate(y[split.validation],p,scale)
                                scores[model] = metrics['mae']
                                inner.append(dict(**base, strategy=design, model=model, train_n=len(split.train),
                                    eval_n=len(split.validation), history_iqr=scale, seconds=seconds, **metrics))
                                case_predictions.append(pd.DataFrame(dict(**base, stage='inner', strategy=design,
                                    model=model, origin_grid_index=split.validation, origin=index[split.validation],
                                    y_true=y[split.validation], prediction=p)))
                            winner = min(f.MODELS,key=lambda model:(scores[model],f.MODELS.index(model)))
                            decisions.append(dict(**base,strategy=design,selected_model=winner,
                                inner_selection_mae=scores[winner], inner_mae_all_candidates=scores))
                            manifest['new_model_fits']=count; save_manifest()
                            print(f'{count}/384 fits complete: {name} {label} O={o} L={l} {design}',flush=True)
                        lock_time = utc()
                        for decision in decisions:
                            decision.update(locked_utc=lock_time,last_inner_fit_completed_utc=last_inner_end)
                        locks.extend(decisions)
                        (out/'locked_choices.json').write_text(json.dumps(locks,indent=2))
                        # No future model is submitted until every choice is saved.
                        jobs = {model:executor.submit(worker,model,x,y,history,evaluation) for model in FITTED}
                        for role,ids in [('train',history),('evaluation',evaluation)]:
                            case_assignments.append(pd.DataFrame(dict(**base,stage='future',strategy='common',
                                role=role,origin_grid_index=ids,origin=index[ids])))
                        actual = {}
                        for model in f.MODELS:
                            if model=='persistence': p,seconds = persistence[evaluation],0.
                            else:
                                p,seconds,start,end = jobs[model].result(); count+=1
                                if start < lock_time: raise ValueError('Future fit preceded choice lock.')
                                ledger.append(dict(**base,stage='future',strategy='common',model=model,fit_id=count,
                                    train_n=len(history),eval_n=len(evaluation),started_utc=start,
                                    completed_utc=end,seconds=seconds,cache_used=False))
                            metrics = f.evaluate(y[evaluation],p,scale); actual[model]=metrics
                            future.append(dict(**base,model=model,train_n=len(history),eval_n=len(evaluation),
                                history_iqr=scale,seconds=seconds,**metrics))
                            case_predictions.append(pd.DataFrame(dict(**base,stage='future',strategy='common',
                                model=model,origin_grid_index=evaluation,origin=index[evaluation],
                                y_true=y[evaluation],prediction=p)))
                        oracle = min(m['mae'] for m in actual.values())
                        for choice in decisions:
                            metrics = actual[choice['selected_model']]
                            selected.append(dict(**{k:v for k,v in choice.items() if k!='inner_mae_all_candidates'},
                                history_iqr=scale, future_mae=metrics['mae'],future_rmse=metrics['rmse'],
                                future_normalized_mae=metrics['normalized_mae'],oracle_mae=oracle,
                                normalized_selection_regret=(metrics['mae']-oracle)/scale if scale>0 else np.nan))
                        token=f'{name}_{label}_O{o}_L{l}'
                        pred_path=out/'checkpoints'/f'{token}_predictions.csv.gz'
                        split_path=out/'checkpoints'/f'{token}_splits.csv.gz'
                        export_audit[str(pred_path.relative_to(out))]=write_union_csv_gz(case_predictions,pred_path)
                        export_audit[str(split_path.relative_to(out))]=write_union_csv_gz(case_assignments,split_path)
                        prediction_shards.append(pred_path);assignment_shards.append(split_path)
                        (out/'export_audit.json').write_text(json.dumps(export_audit,indent=2))
                        for filename,rows in [('inner_candidate_metrics.csv',inner),('future_candidate_metrics.csv',future),
                            ('selected_procedure_metrics.csv',selected),('fit_ledger.csv',ledger)]:
                            pd.DataFrame(rows).to_csv(out/filename,index=False)
                        manifest['new_model_fits']=count; save_manifest()
                        print(f'{count}/384 fits complete: {name} {label} O={o} L={l} common refit saved',flush=True)
        # Each final table has one union schema, one gzip stream and a verified atomic write.
        tables={'feature_snapshots.csv.gz':snapshots,'maturity_audit.csv.gz':maturity,'scale_membership.csv.gz':scale_records}
        for filename,frames in tables.items():export_audit[filename]=write_union_csv_gz(frames,out/filename)
        for filename,paths in [('predictions.csv.gz',prediction_shards),('split_assignments.csv.gz',assignment_shards)]:
            if paths:
                frames=[pd.read_csv(path,float_precision='round_trip',low_memory=False) for path in paths]
                export_audit[filename]=write_union_csv_gz(frames,out/filename)
        (out/'export_audit.json').write_text(json.dumps(export_audit,indent=2))
        difference,contrast=derive_comparisons(pd.DataFrame(selected))
        difference.to_csv(out/'selection_differences.csv',index=False)
        contrast.to_csv(out/'primary_and_secondary_contrasts.csv',index=False)
        feasible=sum(row['status']=='feasible' for row in cases)
        if count!=24*feasible: raise ValueError('Unexpected fit accounting.')
        manifest.update(status='complete', completed_utc=utc(),new_model_fits=count,
            elapsed_seconds=time.perf_counter()-run_start,feasible_cases=feasible,infeasible_cases=len(cases)-feasible,
            inner_candidate_rows=len(inner),future_candidate_rows=len(future),selected_procedure_rows=len(selected),
            setting_seed_difference_rows=len(difference),contrast_rows=len(contrast))
        save_manifest(); print(json.dumps(manifest,indent=2),flush=True)
    except BaseException as exc:
        manifest.update(status='failed',error=repr(exc),new_model_fits=count,failed_utc=utc())
        save_manifest(); raise

if __name__=='__main__': main()
