import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import forecast_pilot as f
import metadata_preflight as metadata

class ImplementationChecks(unittest.TestCase):
    def frame(self):
        index=pd.date_range('2020-01-01',periods=250,freq='h')
        return pd.DataFrame({'cnt':np.arange(250,dtype=float),'temp':np.arange(250,dtype=float),
                             'hum':.5,'windspeed':.2,'weathersit':'1'},index=index)

    def test_snapshots_respect_target_delay_and_covariate_completion(self):
        frame=self.frame();t=frame.index[200]
        for d in (0,6,24):
            x,p,used=f.build_features(frame,'bike',d)
            self.assertEqual(x.loc[t,'target_lag_1'],199-d)
            self.assertEqual(x.loc[t,'observed_temp'],199)
            self.assertEqual(p[200],199-d);self.assertEqual(used[200],frame.index[199-d])

    def test_unavailable_changes_cannot_change_target_snapshot(self):
        frame=self.frame();t=frame.index[200]
        a,p,_=f.build_features(frame,'bike',24)
        changed=frame.copy();changed.loc[frame.index[176]:,'cnt']=-999
        b,q,_=f.build_features(changed,'bike',24)
        pd.testing.assert_series_equal(a.loc[t],b.loc[t]);self.assertEqual(p[200],q[200])

    def test_missing_hours_are_not_shifted_or_interpolated(self):
        frame=self.frame();frame.loc[frame.index[199],'cnt']=np.nan
        x,p,used=f.build_features(frame,'bike',0)
        self.assertTrue(np.isnan(x.iloc[200].target_lag_1))
        self.assertEqual(p[200],198);self.assertEqual(used[200],frame.index[198])

    def test_preprocessing_statistics_use_only_training(self):
        x=pd.DataFrame({'value':[0.,2.,np.nan,1000.],'category':['a','a','a','new']})
        pipeline=f.model_pipeline('Ridge',x);pre=pipeline.named_steps['preprocess']
        pre.fit(x.iloc[:3]);pre.transform(x.iloc[3:])
        numeric=pre.named_transformers_['numeric']
        self.assertEqual(numeric.named_steps['impute'].statistics_[0],1.)
        self.assertEqual(numeric.named_steps['scale'].mean_[0],1.)
        self.assertEqual(list(pre.named_transformers_['categorical'].named_steps['encode'].categories_[0]),['a'])

    def test_fixed_candidate_parameters(self):
        x=self.frame()[['temp']]
        ridge=f.model_pipeline('Ridge',x).named_steps['model']
        self.assertEqual((ridge.alpha,ridge.solver,ridge.tol,ridge.max_iter),(1.,'lsqr',1e-6,10000))
        rf=f.model_pipeline('RF',x).named_steps['model'];self.assertEqual((rf.n_estimators,rf.min_samples_leaf,rf.random_state),(100,5,42))
        hgb=f.model_pipeline('HGB',x).named_steps['model'];self.assertEqual((hgb.max_iter,hgb.max_leaf_nodes,hgb.early_stopping),(100,15,False))

    def test_reserved_targets_never_converted_by_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'source_archives').mkdir()
            frame=self.frame().iloc[:24].copy();frame['dteday']='2020-01-01';frame['hr']=np.arange(24)
            frame['cnt']=frame.cnt.astype(object)
            frame.loc[frame.index[16]:,'cnt']='RESERVED_VALUE_MUST_NOT_BE_PARSED'
            payload=frame.to_csv(index=False).encode()
            path=root/'source_archives/bike_official.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('hour.csv',payload)
            _,_,digest=metadata.timestamps(path,'bike')
            meta={'datasets':{'bike':{'archive_sha256':f.sha(path),'selected_csv_sha256':digest,
                  'plan':{'start':'2020-01-01 00:00:00','reserved_start':'2020-01-01 16:00:00'}}}}
            loaded,audit=f.load_development('bike',meta,root)
            self.assertEqual(len(loaded),16);self.assertEqual(audit['reserved_source_rows_not_loaded'],8)
            self.assertTrue(np.isfinite(loaded.cnt).all());self.assertEqual(loaded.cnt.max(),15.)

    def test_zero_scale_and_nonfinite_scores(self):
        self.assertTrue(np.isnan(f.evaluate(np.array([1.]),np.array([2.]),0)['normalized_mae']))
        with self.assertRaises(ValueError):f.evaluate(np.array([1.]),np.array([np.nan]),1)

if __name__=='__main__':unittest.main(verbosity=2)
