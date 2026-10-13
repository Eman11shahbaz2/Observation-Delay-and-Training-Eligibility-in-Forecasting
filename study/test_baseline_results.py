"""Independent reconstruction of the completed run from its persisted evidence."""
import json
import csv
import gzip
import io
import zipfile
import zlib
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import expansion_api as f
import replay_core as core

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'baseline_results'
KEY=['dataset','period','O','L']
SEEDS=(42,43,44,45,46)
SETTINGS=((0,0),(0,24),(24,0),(24,24))

def read(name,**kwargs):
    return pd.read_csv(OUT/name,float_precision='round_trip',low_memory=False,**kwargs)

class CompletedExperimentChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((OUT/'run_manifest.json').read_text())
        cls.freeze=json.loads((OUT/'IMPLEMENTATION_FREEZE.json').read_text())
        cls.meta=json.loads((ROOT/'TIMESTAMP_PREFLIGHT.json').read_text())
        cls.cases=read('case_audit.csv')
        cls.inner=read('inner_candidate_metrics.csv')
        cls.future=read('future_candidate_metrics.csv')
        cls.selected=read('selected_procedure_metrics.csv')
        cls.fit=read('fit_ledger.csv')
        cls.diff=read('selection_differences.csv')
        cls.contrasts=pd.DataFrame()
        cls.pred=read('predictions.csv.gz')
        cls.splits=read('split_assignments.csv.gz')
        cls.snap=read('feature_snapshots.csv.gz',dtype={'observed_weather_main':'str'})
        cls.maturity=read('maturity_audit.csv.gz')
        cls.scale=read('scale_membership.csv.gz')
        cls.locks=json.loads((OUT/'locked_choices.json').read_text())
        cls.loaded={name:f.load_development(name,cls.meta,ROOT) for name in ('traffic',)}
        cls.prepared={}
        for name,(frame,audit) in cls.loaded.items():
            y=core.exact_targets(frame[f.CONFIG[name]['target']],frame.index).to_numpy(dtype=float)
            features={o:f.build_features(frame,name,o) for o in (0,24)}
            valid=np.isfinite(y)&np.isfinite(features[0][1])&np.isfinite(features[24][1])
            cls.prepared[name]=(y,features,valid)
        cls.split_groups={key:g for key,g in cls.splits.groupby(KEY+['stage','strategy','role'],sort=False)}

    def test_complete_fit_accounting_and_output_cardinality(self):
        self.assertEqual(self.manifest['status'],'complete')
        self.assertEqual(self.manifest['new_model_fits'],24)
        self.assertEqual(self.manifest['cached_model_fits'],0)
        self.assertEqual(self.manifest['combined_maximum_new_fits'],24)
        self.assertLessEqual(self.manifest['combined_maximum_new_fits'],384)
        audit=json.loads((ROOT/'INTERRUPTION_AUDIT.json').read_text())
        self.assertEqual(f.sha(ROOT/'reference/initial_expansion_runner.py'),audit['initial_runner_sha256'])
        self.assertFalse(audit['first_case_complete_checkpoint_saved'])
        self.assertEqual(len(self.cases),1);self.assertTrue((self.cases.status=='feasible').all())
        for frame,n in [(self.inner,28),(self.future,4),(self.selected,7),(self.diff,5),(self.contrasts,0),(self.fit,24)]:
            self.assertEqual(len(frame),n)
        np.testing.assert_array_equal(np.sort(self.fit.fit_id),np.arange(1,25))
        self.assertFalse(self.fit.cache_used.any())
        self.assertEqual(set(self.fit.model),{'Ridge','RF','HGB'})
        for _,g in self.fit.groupby(KEY):
            self.assertEqual(len(g),24);self.assertEqual(sum(g.stage=='inner'),21)
            self.assertEqual(sum(g.stage=='future'),3)
        self.assertFalse(self.pred.duplicated(KEY+['stage','strategy','model','origin_grid_index']).any())
        self.assertFalse(self.splits.duplicated(KEY+['stage','strategy','role','origin_grid_index']).any())

    def test_protocol_code_and_source_integrity(self):
        for name,digest in self.freeze['sha256'].items(): self.assertEqual(f.sha(ROOT/name),digest,name)
        for name,info in self.meta['datasets'].items():
            self.assertEqual(f.sha(ROOT/'source_archives'/f'{name}_official.zip'),info['archive_sha256'])
        self.assertEqual(f.sha(ROOT/'forecast_pilot.py'),'4024e96573198d22e2cefc6e720865dbfa1da9dd8f82866d9b8bcd1939cbb5f7')
        prior=json.loads((ROOT/'EXPANSION_FREEZE.json').read_text())
        for name,digest in prior['code_or_protocol_sha256'].items(): self.assertEqual(f.sha(ROOT/name),digest,name)
        self.assertTrue((pd.to_datetime(self.fit.started_utc,utc=True)>=pd.Timestamp(self.freeze['frozen_utc'])).all())

    def test_reserved_targets_and_future_windows_are_excluded(self):
        self.assertEqual(self.manifest['reserved_target_rows_loaded'],0)
        self.assertFalse(self.manifest['reserved_windows_scored'])
        audit=json.loads((OUT/'dataset_audit.json').read_text())
        for name,(frame,loaded) in self.loaded.items():
            saved=next(row for row in audit if row['dataset']==name)
            for key,value in loaded.items(): self.assertEqual(saved[key],value)
            boundary=pd.Timestamp(self.meta['datasets'][name]['plan']['reserved_start'])
            self.assertLess(frame.index.max(),boundary)
            pred=self.pred[self.pred.dataset==name]
            self.assertTrue((pd.to_datetime(pred.origin)+pd.Timedelta(hours=7)<=boundary).all())
            expected_reserved={'traffic':12700,'household':415023}[name]
            self.assertEqual(saved['reserved_source_rows_not_loaded'],expected_reserved)

    def test_as_of_feature_snapshots_rebuild_from_guarded_sources(self):
        for name,(frame,_) in self.loaded.items():
            y,features,valid=self.prepared[name]
            for o,(x,p,used) in features.items():
                saved=self.snap[(self.snap.dataset==name)&(self.snap.O==o)].sort_values('origin_grid_index')
                np.testing.assert_array_equal(saved.origin_grid_index,np.arange(len(frame)))
                np.testing.assert_array_equal(pd.to_datetime(saved.origin),frame.index)
                for col in x:
                    if pd.api.types.is_numeric_dtype(x[col]):
                        np.testing.assert_allclose(saved[col].to_numpy(),x[col].to_numpy(),rtol=0,atol=0,equal_nan=True)
                    else:
                        np.testing.assert_array_equal(saved[col].fillna('__MISSING__').to_numpy(),x[col].fillna('__MISSING__').to_numpy())
                np.testing.assert_allclose(saved.persistence,p,rtol=0,atol=0,equal_nan=True)
                np.testing.assert_array_equal(pd.DatetimeIndex(pd.to_datetime(saved.persistence_source_timestamp)).asi8,used.asi8)
                np.testing.assert_array_equal(saved.eligible_origin,valid)
                legal=np.isfinite(p)
                self.assertTrue((used[legal]+pd.Timedelta(hours=1+o)<=frame.index[legal]).all())

    def test_every_maturity_record_matches_the_two_clocks(self):
        for (name,o,l),group in self.maturity.groupby(['dataset','O','L']):
            origin=pd.DatetimeIndex(pd.to_datetime(group.origin))
            np.testing.assert_array_equal(pd.to_datetime(group.target_hour),origin+pd.Timedelta(hours=6))
            np.testing.assert_array_equal(pd.to_datetime(group.physical_target_arrival),origin+pd.Timedelta(hours=7+o))
            np.testing.assert_array_equal(pd.to_datetime(group.label_usable_at),origin+pd.Timedelta(hours=7+o+l))
            np.testing.assert_array_equal(group.eligible_origin,self.prepared[name][2])

    def test_every_saved_split_reconstructs_with_exact_counts_and_maturity(self):
        for row in self.cases[self.cases.status=='feasible'].itertuples():
            base=(row.dataset,row.period,row.O,row.L)
            index=self.loaded[row.dataset][0].index
            valid=self.prepared[row.dataset][2]
            a,b,c=map(pd.Timestamp,(row.inner_cut,row.outer_cut,row.future_end))
            ready=index+pd.Timedelta(hours=7+row.O+row.L)
            train=np.flatnonzero(valid&(index<a)&(ready<=a))
            validation=np.flatnonzero(valid&(index>=a)&(index<b)&(ready<=b))
            pool=np.r_[train,validation]
            n=len(validation)
            expected={'chronological':(train,validation),
                      'earlier_validation':(np.sort(pool)[n:],np.sort(pool)[:n])}
            for seed in SEEDS:
                shuffled=np.random.default_rng(seed).permutation(pool)
                expected[f'random_{seed}']=(shuffled[n:],shuffled[:n])
            for strategy,(tr,va) in expected.items():
                self.assertEqual((len(tr),len(va)),(row.inner_train_n,row.inner_validation_n))
                for role,ids in [('train',tr),('validation',va)]:
                    saved=self.split_groups[base+('inner',strategy,role)]
                    np.testing.assert_array_equal(saved.origin_grid_index,ids)
                    np.testing.assert_array_equal(pd.to_datetime(saved.origin),index[ids])
                    self.assertTrue((ready[ids]<=b).all())
            history=np.flatnonzero(valid&(index<b)&(ready<=b))
            future=np.flatnonzero(valid&(index>=b)&(index<c)&(index+pd.Timedelta(hours=7)<=c))
            for role,ids in [('train',history),('evaluation',future)]:
                saved=self.split_groups[base+('future','common',role)]
                np.testing.assert_array_equal(saved.origin_grid_index,ids)
            self.assertEqual((len(history),len(future)),(row.common_history_n,row.future_n))

    def test_historical_scale_uses_only_maximum_maturity_labels(self):
        for (name,period),group in self.cases.groupby(['dataset','period']):
            b=pd.Timestamp(group.outer_cut.iloc[0])
            index=self.loaded[name][0].index;y,_,valid=self.prepared[name]
            ids=np.flatnonzero(valid&(index<b)&(index+pd.Timedelta(hours=55)<=b))
            saved=self.scale[(self.scale.dataset==name)&(self.scale.period==period)]
            np.testing.assert_array_equal(saved.origin_grid_index,ids)
            np.testing.assert_array_equal(saved.y_true,y[ids])
            q=np.quantile(y[ids],[.25,.75]);scale=float(q[1]-q[0])
            self.assertTrue((group.history_iqr==scale).all())
            self.assertTrue((group.scale_history_n==len(ids)).all())

    def test_all_prediction_metrics_membership_and_targets_recompute(self):
        inner_index=self.inner.set_index(KEY+['strategy','model'])
        future_index=self.future.set_index(KEY+['model'])
        groups=self.pred.groupby(KEY+['stage','strategy','model'],sort=False)
        self.assertEqual(len(groups),32)
        for key,g in groups:
            name,period,o,l,stage,strategy,model=key
            ids=g.origin_grid_index.to_numpy(dtype=int)
            np.testing.assert_array_equal(g.y_true,self.prepared[name][0][ids])
            role='validation' if stage=='inner' else 'evaluation'
            expected=self.split_groups[key[:4]+(stage,strategy,role)].origin_grid_index
            np.testing.assert_array_equal(ids,expected)
            row=inner_index.loc[key[:4]+(strategy,model)] if stage=='inner' else future_index.loc[key[:4]+(model,)]
            self.assertEqual(len(ids),row.eval_n)
            mae=np.mean(np.abs(g.y_true.to_numpy()-g.prediction.to_numpy()))
            rmse=np.sqrt(np.mean((g.y_true.to_numpy()-g.prediction.to_numpy())**2))
            self.assertAlmostEqual(mae,row.mae,places=11)
            self.assertAlmostEqual(rmse,row.rmse,places=11)
            self.assertAlmostEqual(mae/row.history_iqr,row.normalized_mae,places=12)
            if model=='persistence':
                np.testing.assert_array_equal(g.prediction,self.prepared[name][1][o][1][ids])

    def test_every_choice_is_inner_only_locked_before_future_fitting(self):
        self.assertEqual(len(self.locks),7)
        inner=self.inner.set_index(KEY+['strategy','model'])
        future=self.future.set_index(KEY+['model'])
        selected=self.selected.set_index(KEY+['strategy'])
        for choice in self.locks:
            base=tuple(choice[k] for k in KEY);strategy=choice['strategy']
            scores={model:float(inner.loc[base+(strategy,model),'mae']) for model in f.MODELS}
            self.assertEqual(scores,choice['inner_mae_all_candidates'])
            winner=min(f.MODELS,key=lambda model:(scores[model],f.MODELS.index(model)))
            self.assertEqual(winner,choice['selected_model'])
            self.assertEqual(scores[winner],choice['inner_selection_mae'])
            fit=self.fit
            mask=np.logical_and.reduce([fit[k].to_numpy()==v for k,v in zip(KEY,base)])
            fit=fit[mask];lock=pd.Timestamp(choice['locked_utc'])
            self.assertTrue((pd.to_datetime(fit[fit.stage=='inner'].completed_utc,utc=True)<=lock).all())
            self.assertTrue((pd.to_datetime(fit[fit.stage=='future'].started_utc,utc=True)>lock).all())
            self.assertEqual(pd.to_datetime(fit[fit.stage=='inner'].completed_utc,utc=True).max(),pd.Timestamp(choice['last_inner_fit_completed_utc']))
            row=selected.loc[base+(strategy,)]
            mae=future.loc[base+(winner,),'mae'];oracle=min(future.loc[base+(m,),'mae'] for m in f.MODELS)
            self.assertEqual(row.selected_model,winner);self.assertEqual(row.future_mae,mae)
            self.assertEqual(row.oracle_mae,oracle)
            self.assertAlmostEqual(row.normalized_selection_regret,(mae-oracle)/row.history_iqr,places=13)

    def test_prepared_targets_independently_reconstruct_from_raw_prefix(self):
        audits=json.loads((OUT/'dataset_audit.json').read_text())
        for name,(frame,_) in self.loaded.items():
            meta=self.meta['datasets'][name]
            with zipfile.ZipFile(ROOT/'source_archives'/f'{name}_official.zip') as archive:
                payload=archive.read(meta['selected_member'])
            if meta['selected_member'].endswith('.gz'):payload=gzip.decompress(payload)
            dates=f.CONFIG[name]['dates'];target=f.CONFIG[name]['target']
            raw=pd.read_csv(io.BytesIO(payload),sep=',' if name=='traffic' else ';',
                usecols=dates+[target],nrows=meta['development_source_timestamp_rows'],dtype=str,keep_default_na=False)
            times=pd.DatetimeIndex(pd.to_datetime(raw.date_time,format='%Y-%m-%d %H:%M:%S')) if name=='traffic' else pd.DatetimeIndex(pd.to_datetime(raw.Date+' '+raw.Time,format='%d/%m/%Y %H:%M:%S'))
            self.assertTrue((times<pd.Timestamp(meta['plan']['reserved_start'])).all())
            values=pd.to_numeric(raw[target],errors='coerce').to_numpy(dtype=float)
            valid=np.isfinite(values)&(values>=0)
            if name=='traffic':valid &= values==np.floor(values)
            values[~valid]=np.nan
            groups=pd.Series(values,index=times if name=='traffic' else times.floor('h')).groupby(level=0)
            stats=groups.agg(['size','count','min','max','mean'])
            if name=='traffic':
                expected=stats['min'].where((stats['count']==stats['size'])&(stats['min']==stats['max']))
            else:
                expected=stats['mean'].where((stats['size']==60)&(stats['count']==60))
            expected=expected.reindex(frame.index)
            np.testing.assert_allclose(frame[target],expected,rtol=1e-14,atol=1e-14,equal_nan=True)
            saved=next(a for a in audits if a['dataset']==name)
            diagnostics=saved['raw_development_diagnostics']
            self.assertEqual(diagnostics['raw_target_invalid_or_missing_n'],int((~valid).sum()))
            self.assertEqual(diagnostics['raw_target_rows_parsed'],len(raw))
            self.assertEqual(diagnostics['reserved_target_rows_parsed'],0)
            self.assertEqual(saved['finite_hourly_target_n'],int(np.isfinite(expected).sum()))
            if name=='traffic':
                self.assertEqual(sum(diagnostics[k] for k in ['duplicate_target_consensus_groups','duplicate_target_conflict_groups','duplicate_target_invalid_or_missing_groups']),int((stats['size']>1).sum()))
            else:
                self.assertEqual(diagnostics['complete_clock_hours_with_missing_or_invalid_target_minutes'],int(((stats['size']==60)&(stats['count']<60)).sum()))

    def test_combined_exports_have_one_valid_stream_and_union_schema(self):
        audit=json.loads((OUT/'export_audit.json').read_text())
        frames={'feature_snapshots.csv.gz':self.snap,'maturity_audit.csv.gz':self.maturity,
            'scale_membership.csv.gz':self.scale,'predictions.csv.gz':self.pred,'split_assignments.csv.gz':self.splits}
        for name,frame in frames.items():
            decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
            decoder.decompress((OUT/name).read_bytes());decoder.flush()
            self.assertTrue(decoder.eof,name);self.assertEqual(decoder.unused_data,b'',name)
            with gzip.open(OUT/name,'rt',newline='') as stream:
                reader=csv.reader(stream);header=next(reader)
                self.assertEqual(header,list(frame.columns));self.assertEqual(len(header),len(set(header)))
                count=0
                for row in reader:
                    self.assertEqual(len(row),len(header));self.assertNotEqual(row,header);count+=1
            self.assertEqual(count,len(frame));self.assertEqual(count,audit[name]['rows'])
        expected=set()
        for name,(_,features,_) in self.prepared.items():expected.update(features[0][0].columns)
        self.assertTrue(expected.issubset(self.snap.columns))

    def test_numerical_feasibility_matches_all_saved_cases(self):
        numeric=read('numerical_feasibility.csv').set_index(KEY)
        cases=self.cases.set_index(KEY)
        self.assertEqual(set(numeric.index),set(cases.index))
        for col in ['inner_train_n','inner_validation_n','common_history_n','future_n']:
            pd.testing.assert_series_equal(numeric[col].sort_index(),cases[col].sort_index())
        self.assertEqual(self.manifest['numerical_feasible_cases'],1)
        self.assertEqual(self.manifest['numerical_infeasible_cases'],0)
        for key,group in self.split_groups.items():
            if key[4]=='inner' and key[6]=='train':
                self.assertGreaterEqual(len(np.unique(self.prepared[key[0]][0][group.origin_grid_index])),2)

    def test_all_declared_primary_and_secondary_contrasts_recompute(self):
        selected=self.selected.set_index(KEY+['strategy'])
        differences=self.diff.set_index(KEY+['seed'])
        for row in self.diff.itertuples():
            base=(row.dataset,row.period,row.O,row.L)
            ch=selected.loc[base+('chronological',)];rand=selected.loc[base+(f'random_{row.seed}',)]
            early=selected.loc[base+('earlier_validation',)]
            self.assertEqual(row.chronological_model,ch.selected_model)
            self.assertEqual(row.random_model,rand.selected_model)
            self.assertEqual(row.earlier_validation_model,early.selected_model)
            self.assertAlmostEqual(row.delta_chron_minus_random,ch.normalized_selection_regret-rand.normalized_selection_regret,places=13)
            self.assertAlmostEqual(row.earlier_minus_random,early.normalized_selection_regret-rand.normalized_selection_regret,places=13)
            self.assertAlmostEqual(row.earlier_minus_chron,early.normalized_selection_regret-ch.normalized_selection_regret,places=13)
        for row in self.contrasts.itertuples():
            ds=[differences.loc[(row.dataset,row.period,o,l,row.seed),'delta_chron_minus_random'] if (row.dataset,row.period,o,l,row.seed) in differences.index else np.nan for o,l in SETTINGS]
            d00,d024,d240,d2424=ds
            for value,expected in [(row.primary_C,d240-d024),(row.measurement_effect,d240-d00),
                (row.fitting_use_effect,d024-d00),(row.factorial_interaction,(d2424-d240)-(d024-d00))]:
                if np.isnan(expected): self.assertTrue(np.isnan(value))
                else: self.assertAlmostEqual(value,expected,places=13)

if __name__=='__main__': unittest.main(verbosity=2)
