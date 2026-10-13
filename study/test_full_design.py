import unittest
import numpy as np
import pandas as pd
import forecast_pilot as f
import replay_core as core
import run_full_experiment as run

class FullDesignChecks(unittest.TestCase):
    def setUp(self):
        self.index=pd.date_range('2020-01-01',periods=1000,freq='h')
        self.a,self.b,self.c=self.index[600],self.index[800],self.index[950]
        self.frame=pd.DataFrame(dict(cnt=np.arange(1000,dtype=float),temp=1.,hum=.5,windspeed=.2,
                                    weathersit='1'),index=self.index)

    def test_training_use_delay_does_not_change_features(self):
        snapshots={}
        for o,l in run.SETTINGS:
            snapshots[o,l]=f.build_features(self.frame,'bike',o)
        for o in (0,24):
            pd.testing.assert_frame_equal(snapshots[o,0][0],snapshots[o,24][0])
            np.testing.assert_array_equal(snapshots[o,0][1],snapshots[o,24][1])

    def test_observation_delay_changes_both_feature_and_label_clocks(self):
        x0,_,_=f.build_features(self.frame,'bike',0)
        x24,_,_=f.build_features(self.frame,'bike',24)
        self.assertEqual(x0.iloc[500].target_lag_1-x24.iloc[500].target_lag_1,24.)
        self.assertEqual(core.label_ready(self.index,24)[500]-core.label_ready(self.index,0)[500],pd.Timedelta(hours=24))

    def test_primary_pair_has_equal_memberships_but_different_inputs(self):
        first=core.chronological_split(self.index,self.a,self.b,self.c,0+24)
        second=core.chronological_split(self.index,self.a,self.b,self.c,24+0)
        for (_,s),(_,t) in zip(run.selectors(first),run.selectors(second)):
            for attr in ('train','validation','common_history','future'):
                np.testing.assert_array_equal(getattr(s,attr),getattr(t,attr))
        x0,_,_=f.build_features(self.frame,'bike',0);x24,_,_=f.build_features(self.frame,'bike',24)
        self.assertNotEqual(x0.iloc[500].target_lag_1,x24.iloc[500].target_lag_1)

    def test_earlier_validation_is_sorted_size_matched_exact_union(self):
        ch=core.chronological_split(self.index,self.a,self.b,self.c,48)
        early=run.earlier_split(ch)
        self.assertEqual((len(ch.train),len(ch.validation)),(len(early.train),len(early.validation)))
        self.assertLess(early.validation.max(),early.train.min())
        np.testing.assert_array_equal(np.sort(np.r_[early.train,early.validation]),np.sort(np.r_[ch.train,ch.validation]))
        self.assertFalse(set(early.train)&set(early.validation))

    def test_all_maturity_and_future_boundaries_and_random_seeds(self):
        futures=[]
        for o,l in run.SETTINGS:
            ch=core.chronological_split(self.index,self.a,self.b,self.c,o+l)
            self.assertTrue((core.label_ready(self.index[ch.train],o+l)<=self.a).all())
            self.assertTrue((core.label_ready(self.index[ch.common_history],o+l)<=self.b).all())
            designs=run.selectors(ch);self.assertEqual(len(designs),7)
            for _,s in designs:
                pool=np.r_[s.train,s.validation]
                self.assertTrue((core.label_ready(self.index[pool],o+l)<=self.b).all())
                futures.append(s.future)
            self.assertEqual(len({tuple(s.validation) for name,s in designs if name.startswith('random')}),5)
        for ids in futures[1:]: np.testing.assert_array_equal(ids,futures[0])
        self.assertTrue((self.index[futures[0]]+pd.Timedelta(hours=7)<=self.c).all())

    def test_declared_contrast_algebra_and_early_comparisons(self):
        rows=[]
        for o,l in run.SETTINGS:
            for name in ['chronological','earlier_validation']+[f'random_{s}' for s in run.SEEDS]:
                regret=(o/24+2*l/24) if name=='chronological' else (4. if name=='earlier_validation' else 0.)
                rows.append(dict(dataset='synthetic',period='T1',O=o,L=l,strategy=name,selected_model='RF',
                                 future_mae=1.+regret,normalized_selection_regret=regret))
        difference,contrast=run.derive_comparisons(pd.DataFrame(rows))
        self.assertEqual(len(difference),20);self.assertEqual(len(contrast),5)
        np.testing.assert_array_equal(contrast.primary_C,np.full(5,-1.))
        np.testing.assert_array_equal(contrast.factorial_interaction,np.zeros(5))
        np.testing.assert_array_equal(contrast.measurement_effect,np.ones(5))
        np.testing.assert_array_equal(contrast.fitting_use_effect,np.full(5,2.))

if __name__=='__main__': unittest.main(verbosity=2)
