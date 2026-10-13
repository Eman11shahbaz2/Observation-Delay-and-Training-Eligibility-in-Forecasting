"""Independent reconstruction of the single reserved evaluation and completion."""
import csv
import gzip
import io
import json
from pathlib import Path
import unittest
import zipfile
import zlib
import numpy as np
import pandas as pd
import study_api as f
import replay_core as core
from run_full_experiment import SETTINGS,SEEDS

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'final_results'
KEY=['dataset','period','O','L']
def read(name,**kwargs):return pd.read_csv(OUT/name,float_precision='round_trip',low_memory=False,**kwargs)

class FinalResultChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((OUT/'run_manifest.json').read_text());cls.freeze=f.verify_release(ROOT)
        cls.plan=json.loads((ROOT/'FINAL_PLAN.json').read_text());cls.choices=json.loads((ROOT/'FINAL_CHOICES.json').read_text())
        cls.cases=read('case_audit.csv');cls.metrics=read('candidate_metrics.csv');cls.selected=read('selected_procedure_metrics.csv')
        cls.fit=read('fit_ledger.csv');cls.pred=read('predictions.csv.gz');cls.splits=read('split_assignments.csv.gz')
        cls.scale=read('scale_membership.csv.gz');cls.maturity=read('maturity_audit.csv.gz')
        cls.snap=read('feature_snapshots.csv.gz',dtype={'observed_weathersit':'str','observed_wd':'str','observed_weather_main':'str'})
        cls.diff=read('selection_differences.csv');cls.contrasts=read('primary_and_secondary_contrasts.csv')
        cls.loaded={name:f.load_full(name,ROOT,allow_reserved=True) for name in f.NAMES};cls.prepared={}
        for name,(frame,_) in cls.loaded.items():
            index=frame.index;y=core.exact_targets(frame[f.CONFIG[name]['target']],index).to_numpy(dtype=float)
            features={o:f.build_features(frame,name,o) for o in (0,24)}
            valid=np.isfinite(y)&np.isfinite(features[0][1])&np.isfinite(features[24][1]);cls.prepared[name]=(y,features,valid)
        cls.memberships={key:g for key,g in cls.splits.groupby(KEY+['role'],sort=False)}

    def test_complete_accounting_and_no_selection_refresh(self):
        m=self.manifest;self.assertEqual(m['status'],'complete');self.assertEqual(m['new_model_fits'],48)
        self.assertEqual(m['selection_refresh_fits'],0);self.assertEqual(m['cached_model_fits'],0);self.assertTrue(m['final_windows_scored'])
        for frame,n in [(self.cases,16),(self.metrics,64),(self.selected,112),(self.fit,48),(self.diff,80),(self.contrasts,20)]:self.assertEqual(len(frame),n)
        self.assertTrue((self.cases.status=='feasible').all());self.assertEqual(set(self.contrasts.dataset),set(f.NAMES))
        np.testing.assert_array_equal(np.sort(self.fit.fit_id),np.arange(1,49));self.assertFalse(self.fit.cache_used.any())
        for _,group in self.fit.groupby(KEY):self.assertEqual(set(group.model),{'Ridge','RF','HGB'})
        self.assertFalse(self.pred.duplicated(KEY+['model','origin_grid_index']).any())
        self.assertFalse(self.splits.duplicated(KEY+['role','origin_grid_index']).any())

    def test_freeze_and_original_components_remain_intact(self):
        f.verify_release(ROOT)
        self.assertEqual(f.sha(ROOT/'forecast_pilot.py'),'4024e96573198d22e2cefc6e720865dbfa1da9dd8f82866d9b8bcd1939cbb5f7')
        self.assertEqual(f.sha(ROOT/'replay_core.py'),'efe928cfbac60e8150f7973ad4424d61dd20b7471f15b5fbe1897ce155fb32c7')
        for name in f.NAMES:self.assertEqual(f.sha(ROOT/'source_archives'/f'{name}_official.zip'),f.source_metadata(name)['archive_sha256'])
        self.assertFalse(self.freeze['reserved_numeric_targets_inspected_before_freeze']);self.assertFalse(self.freeze['final_scores_computed_before_freeze'])

    def test_choices_and_history_precede_every_reserved_release_and_fit(self):
        freeze=pd.Timestamp(self.freeze['frozen_utc']);locked=pd.Timestamp(self.choices['locked_utc'])
        marker=json.loads((ROOT/'FINAL_EVALUATION_STARTED.json').read_text());start=pd.Timestamp(marker['started_utc'])
        historical=json.loads((OUT/'PRE_RELEASE_HISTORY_AUDIT.json').read_text());history_end=pd.Timestamp(historical['completed_utc'])
        self.assertEqual(historical['reserved_numeric_targets_loaded'],0);self.assertLessEqual(locked,freeze);self.assertLessEqual(freeze,start)
        self.assertEqual(marker['freeze_sha256'],f.sha(ROOT/'FINAL_FREEZE.json'))
        audits=json.loads((OUT/'dataset_audit.json').read_text())
        for audit in audits:
            self.assertGreaterEqual(pd.Timestamp(audit['released_utc']),history_end)
            self.assertGreater(audit['reserved_numeric_measurement_rows_converted'],0)
            self.assertTrue(audit['explicit_release_after_freeze'])
            for key,value in self.loaded[audit['dataset']][1].items():self.assertEqual(audit[key],value)
        self.assertTrue((pd.to_datetime(self.fit.started_utc,utc=True)>=history_end).all())
        self.assertTrue((pd.to_datetime(self.fit.started_utc,utc=True)>locked).all())

    def test_every_split_is_legal_and_common_futures_match(self):
        for row in self.cases.itertuples():
            name=row.dataset;index=self.loaded[name][0].index;y,_,valid=self.prepared[name]
            b,c=map(pd.Timestamp,(row.outer_cut,row.future_end));ready=index+pd.Timedelta(hours=7+row.O+row.L)
            train=np.flatnonzero(valid&(index<b)&(ready<=b))
            future=np.flatnonzero(valid&(index>=b)&(index<c)&(index+pd.Timedelta(hours=7)<=c))
            for role,ids in [('train',train),('evaluation',future)]:
                saved=self.memberships[(name,'FINAL',row.O,row.L,role)]
                np.testing.assert_array_equal(saved.origin_grid_index,ids);np.testing.assert_array_equal(pd.to_datetime(saved.origin),index[ids])
            self.assertEqual((len(train),len(future)),(row.train_n,row.future_n));self.assertGreaterEqual(len(np.unique(y[train])),2)
            self.assertTrue((index[train]+pd.Timedelta(hours=7)<=b).all())
        for name in f.NAMES:
            for role in ['train','evaluation']:
                np.testing.assert_array_equal(self.memberships[(name,'FINAL',0,24,role)].origin_grid_index,self.memberships[(name,'FINAL',24,0,role)].origin_grid_index)
            futures=[self.memberships[(name,'FINAL',o,l,'evaluation')].origin_grid_index.to_numpy() for o,l in SETTINGS]
            for ids in futures[1:]:np.testing.assert_array_equal(ids,futures[0])

    def test_historical_scale_and_training_rebuild_from_guarded_development(self):
        audit=json.loads((OUT/'PRE_RELEASE_HISTORY_AUDIT.json').read_text())
        for name in f.NAMES:
            dev,_=f.load_development(name,ROOT);index=dev.index;y=core.exact_targets(dev[f.CONFIG[name]['target']],index).to_numpy(dtype=float)
            prepared={o:f.build_features(dev,name,o) for o in (0,24)};valid=np.isfinite(y)&np.isfinite(prepared[0][1])&np.isfinite(prepared[24][1])
            b=pd.Timestamp(self.plan['datasets'][name]['reserved_start']);ids=np.flatnonzero(valid&(index+pd.Timedelta(hours=55)<=b))
            saved=self.scale[self.scale.dataset==name];np.testing.assert_array_equal(saved.origin_grid_index,ids);np.testing.assert_array_equal(saved.y_true,y[ids])
            q=np.quantile(y[ids],[.25,.75]);scale=float(q[1]-q[0]);self.assertEqual(audit['historical_iqr'][name],scale)
            self.assertTrue((self.cases[self.cases.dataset==name].history_iqr==scale).all())
            for o,l in SETTINGS:
                train=np.flatnonzero(valid&(index+pd.Timedelta(hours=7+o+l)<=b))
                np.testing.assert_array_equal(self.memberships[(name,'FINAL',o,l,'train')].origin_grid_index,train)
                self.assertEqual(audit['train_counts'][name][f'{o},{l}'],len(train))
                pd.testing.assert_frame_equal(self.prepared[name][1][o][0].iloc[train],prepared[o][0].iloc[train],check_freq=False)

    def test_all_as_of_features_and_persistence_reconstruct(self):
        for name,(frame,_) in self.loaded.items():
            for o,(x,p,used) in self.prepared[name][1].items():
                saved=self.snap[(self.snap.dataset==name)&(self.snap.O==o)].sort_values('origin_grid_index')
                np.testing.assert_array_equal(saved.origin_grid_index,np.arange(len(frame)));np.testing.assert_array_equal(pd.to_datetime(saved.origin),frame.index)
                for col in x:
                    if pd.api.types.is_numeric_dtype(x[col]):np.testing.assert_allclose(saved[col],x[col],rtol=0,atol=0,equal_nan=True)
                    else:np.testing.assert_array_equal(saved[col].fillna('__MISSING__'),x[col].fillna('__MISSING__'))
                np.testing.assert_array_equal(saved.persistence,p)
                np.testing.assert_array_equal(pd.DatetimeIndex(pd.to_datetime(saved.persistence_source_timestamp)).asi8,used.asi8)
                np.testing.assert_array_equal(saved.eligible_origin,self.prepared[name][2])
                legal=np.isfinite(p);self.assertTrue((used[legal]+pd.Timedelta(hours=1+o)<=frame.index[legal]).all())

    def test_all_maturity_records_match_physical_and_permission_clocks(self):
        for (name,o,l),group in self.maturity.groupby(['dataset','O','L'],sort=False):
            origin=pd.DatetimeIndex(pd.to_datetime(group.origin));np.testing.assert_array_equal(origin,self.loaded[name][0].index)
            for col,hours in [('target_hour',6),('physical_target_arrival',7+o),('label_usable_at',7+o+l)]:np.testing.assert_array_equal(pd.to_datetime(group[col]),origin+pd.Timedelta(hours=hours))
            np.testing.assert_array_equal(group.eligible_origin,self.prepared[name][2])

    def test_every_prediction_truth_metric_and_membership_recomputes(self):
        metrics=self.metrics.set_index(KEY+['model']);groups=self.pred.groupby(KEY+['model'],sort=False);self.assertEqual(len(groups),64)
        for key,g in groups:
            name,period,o,l,model=key;ids=g.origin_grid_index.to_numpy(dtype=int)
            np.testing.assert_array_equal(g.y_true,self.prepared[name][0][ids]);np.testing.assert_array_equal(ids,self.memberships[key[:4]+('evaluation',)].origin_grid_index)
            row=metrics.loc[key];self.assertEqual(len(g),row.eval_n)
            mae=float(np.mean(np.abs(g.y_true.to_numpy()-g.prediction.to_numpy())));rmse=float(np.sqrt(np.mean((g.y_true.to_numpy()-g.prediction.to_numpy())**2)))
            self.assertAlmostEqual(mae,row.mae,places=11);self.assertAlmostEqual(rmse,row.rmse,places=11)
            if row.history_iqr>0:self.assertAlmostEqual(mae/row.history_iqr,row.normalized_mae,places=12)
            else:self.assertTrue(np.isnan(row.normalized_mae))
            if model=='persistence':np.testing.assert_array_equal(g.prediction,self.prepared[name][1][o][1][ids])

    def test_every_selected_procedure_uses_its_frozen_T2_inner_choice(self):
        selected=self.selected.set_index(KEY+['strategy']);metrics=self.metrics.set_index(KEY+['model'])
        inner=pd.concat([pd.read_csv(ROOT/f'development_reference/{label}/inner_candidate_metrics.csv',float_precision='round_trip') for label in ['earlier','expansion']]).set_index(KEY+['strategy','model'])
        for choice in self.choices['choices']:
            name,o,l,strategy=[choice[k] for k in ['dataset','O','L','strategy']]
            scores={model:float(inner.loc[(name,'T2',o,l,strategy,model),'mae']) for model in f.MODELS}
            self.assertEqual(scores,choice['inner_mae_all_candidates']);winner=min(f.MODELS,key=lambda m:(scores[m],f.MODELS.index(m)))
            self.assertEqual(choice['selected_model'],winner);row=selected.loc[(name,'FINAL',o,l,strategy)]
            self.assertEqual(row.selected_model,winner);self.assertEqual(row.selection_source_period,'T2');self.assertEqual(row.locked_utc,self.choices['locked_utc'])
            candidates=metrics.loc[(name,'FINAL',o,l)];mae=candidates.loc[winner,'mae'];oracle=candidates.mae.min()
            self.assertEqual(row.future_mae,mae);self.assertEqual(row.oracle_mae,oracle)
            self.assertAlmostEqual(row.normalized_selection_regret,(mae-oracle)/row.history_iqr,places=13)

    def test_every_primary_and_secondary_contrast_recomputes(self):
        selected=self.selected.set_index(KEY+['strategy']);diff=self.diff.set_index(KEY+['seed'])
        for row in self.diff.itertuples():
            base=(row.dataset,row.period,row.O,row.L);ch=selected.loc[base+('chronological',)];random=selected.loc[base+(f'random_{row.seed}',)];earlier=selected.loc[base+('earlier_validation',)]
            for value,expected in [(row.delta_chron_minus_random,ch.normalized_selection_regret-random.normalized_selection_regret),(row.earlier_minus_random,earlier.normalized_selection_regret-random.normalized_selection_regret),(row.earlier_minus_chron,earlier.normalized_selection_regret-ch.normalized_selection_regret)]:self.assertAlmostEqual(value,expected,places=13)
        for row in self.contrasts.itertuples():
            a,b,c,d=[diff.loc[(row.dataset,'FINAL',o,l,row.seed),'delta_chron_minus_random'] for o,l in SETTINGS]
            for value,expected in [(row.primary_C,c-b),(row.measurement_effect,c-a),(row.fitting_use_effect,b-a),(row.factorial_interaction,(d-c)-(b-a))]:self.assertAlmostEqual(value,expected,places=13)

    def test_combined_compressed_exports_are_single_valid_streams(self):
        audit=json.loads((OUT/'export_audit.json').read_text())
        for name,frame in [('feature_snapshots.csv.gz',self.snap),('maturity_audit.csv.gz',self.maturity),('split_assignments.csv.gz',self.splits),('scale_membership.csv.gz',self.scale),('predictions.csv.gz',self.pred)]:
            decoder=zlib.decompressobj(16+zlib.MAX_WBITS);decoder.decompress((OUT/name).read_bytes());decoder.flush()
            self.assertTrue(decoder.eof);self.assertEqual(decoder.unused_data,b'')
            with gzip.open(OUT/name,'rt',newline='') as stream:
                rows=csv.reader(stream);header=next(rows);self.assertEqual(header,list(frame.columns));self.assertEqual(len(header),len(set(header)));count=0
                for row in rows:self.assertEqual(len(row),len(header));self.assertNotEqual(row,header);count+=1
            self.assertEqual(count,len(frame));self.assertEqual(count,audit[name]['rows'])

    def test_completed_development_merge_preserves_all_existing_scores(self):
        root=ROOT/'development_results';audit=json.loads((root/'COMPLETION_AUDIT.json').read_text())
        self.assertEqual(audit['complete_expansion_fits'],384);self.assertEqual(audit['reserved_numeric_targets_parsed'],0)
        for name,digest in audit['output_sha256'].items():self.assertEqual(f.sha(ROOT/name),digest)
        for name in ['inner_candidate_metrics.csv','future_candidate_metrics.csv','selected_procedure_metrics.csv']:
            earlier=pd.read_csv(ROOT/'development_reference/expansion'/name,float_precision='round_trip')
            baseline=pd.read_csv(ROOT/'baseline_results'/name,float_precision='round_trip');combined=pd.read_csv(root/name,float_precision='round_trip')
            pd.testing.assert_frame_equal(combined,pd.concat([earlier,baseline],ignore_index=True))
        contrast=pd.read_csv(root/'primary_and_secondary_contrasts.csv',float_precision='round_trip')
        self.assertEqual(len(contrast),20);self.assertFalse(contrast.isna().any().any())

    def test_reserved_target_preparation_independently_reconstructs_from_raw_values(self):
        for name,(frame,audit) in self.loaded.items():
            info=f.source_metadata(name);cfg=f.CONFIG[name];target=cfg['target']
            if name in ('bike','beijing'):
                data=f.original.csv_bytes(ROOT/'source_archives'/f'{name}_official.zip',name)
                times,_,_=f.metadata.timestamps(ROOT/'source_archives'/f'{name}_official.zip',name)
                raw=pd.read_csv(io.BytesIO(data),usecols=[target],dtype=str)
            else:
                with zipfile.ZipFile(ROOT/'source_archives'/f'{name}_official.zip') as archive:payload=archive.read(info['selected_member'])
                data=gzip.decompress(payload) if info['selected_member'].endswith('.gz') else payload
                raw=pd.read_csv(io.BytesIO(data),sep=',' if name=='traffic' else ';',usecols=cfg['dates']+[target],dtype=str,keep_default_na=False)
                times=pd.DatetimeIndex(pd.to_datetime(raw.date_time,format='%Y-%m-%d %H:%M:%S')) if name=='traffic' else pd.DatetimeIndex(pd.to_datetime(raw.Date+' '+raw.Time,format='%d/%m/%Y %H:%M:%S'))
            values=pd.to_numeric(raw[target],errors='coerce').to_numpy(dtype=float)
            start=pd.Timestamp(info['plan']['start']);end=pd.Timestamp(info['plan']['reserved_end_exclusive']);retained=(times>=start)&(times<end)
            times=times[retained];values=values[retained]
            if name in ('traffic','household'):
                legal=np.isfinite(values)&(values>=0)
                if name=='traffic':legal &= values==np.floor(values)
                values[~legal]=np.nan
                if name=='household':self.assertTrue(times.is_unique)
                stats=pd.Series(values,index=times if name=='traffic' else times.floor('h')).groupby(level=0).agg(['size','count','min','max','mean'])
                expected=stats['min'].where((stats['count']==stats['size'])&(stats['min']==stats['max'])) if name=='traffic' else stats['mean'].where((stats['size']==60)&(stats['count']==60))
            else:expected=pd.Series(values,index=times)
            expected=expected.reindex(frame.index)
            np.testing.assert_allclose(frame[target],expected,rtol=1e-14,atol=1e-13,equal_nan=True)
            boundary=pd.Timestamp(info['plan']['reserved_start']);reserved=frame.index>=boundary
            self.assertEqual(int(np.isfinite(expected[reserved]).sum()),audit['reserved_hourly_target_finite'])
            self.assertEqual(int((~np.isfinite(expected[reserved])).sum()),audit['reserved_hourly_target_missing'])

if __name__=='__main__':unittest.main(verbosity=2)
