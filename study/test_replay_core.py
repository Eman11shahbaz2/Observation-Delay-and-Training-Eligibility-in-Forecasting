import unittest
import numpy as np
import pandas as pd
from replay_core import latest_available,exact_targets,label_ready,chronological_split,matched_random_split,calendar_plan,hourly_index

class ReplayChecks(unittest.TestCase):
    def setUp(self):
        self.times=pd.date_range('2020-01-01',periods=200,freq='h')
        self.series=pd.Series(np.arange(200,dtype=float),index=self.times)

    def test_hour_window_and_delay_cutoff(self):
        origin=self.times[100]
        for delay in (0,6,24):
            value,time=latest_available(self.series,origin,delay)
            self.assertEqual(time,self.times[99-delay]);self.assertEqual(value,99-delay)
            self.assertLessEqual(time+pd.Timedelta(hours=1+delay),origin)

    def test_future_and_not_yet_available_changes_do_not_change_snapshot(self):
        origin=self.times[100];before=latest_available(self.series,origin,24)
        changed=self.series.copy();changed.loc[self.times[76]:]=-999
        self.assertEqual(latest_available(changed,origin,24),before)

    def test_missing_exact_future_hour_is_not_next_row(self):
        sparse=self.series.drop(self.times[16])
        self.assertTrue(pd.isna(exact_targets(sparse,[self.times[10]]).iloc[0]))

    def test_stale_limit_and_missing_history(self):
        series=self.series.copy();series.iloc[90:]=np.nan
        self.assertTrue(pd.isna(latest_available(series,self.times[100],0,max_gap_hours=5)[0]))
        self.assertEqual(latest_available(series,self.times[100],0,max_gap_hours=20)[0],89.)

    def test_label_maturity_excludes_boundary_labels(self):
        a,b,c=self.times[80],self.times[130],self.times[160]
        split=chronological_split(self.times,a,b,c,24)
        self.assertTrue((label_ready(self.times[split.train],24)<=a).all())
        self.assertTrue((label_ready(self.times[split.common_history],24)<=b).all())
        self.assertNotIn(79,split.train);self.assertNotIn(129,split.common_history)
        self.assertEqual(set(split.future),set(range(130,154)))

    def test_random_is_size_matched_and_common_future_is_identical(self):
        s=chronological_split(self.times,self.times[80],self.times[130],self.times[160],6)
        r=matched_random_split(s)
        self.assertEqual((len(s.train),len(s.validation)),(len(r.train),len(r.validation)))
        self.assertEqual(set(s.train)|set(s.validation),set(r.train)|set(r.validation))
        self.assertFalse(set(r.train)&set(r.validation))
        np.testing.assert_array_equal(s.common_history,r.common_history);np.testing.assert_array_equal(s.future,r.future)

    def test_plan_depends_only_on_clock_span_not_missing_rows(self):
        self.assertEqual(calendar_plan(self.times),calendar_plan(self.times.delete([10,20,30])))
        plan=calendar_plan(self.times)
        self.assertEqual(plan['reserved_start'],str(self.times[160]))
        self.assertEqual(plan['development'][-1]['future_end'],plan['reserved_start'])

    def test_duplicate_or_unsorted_or_subhour_timestamps_rejected(self):
        for times in [[self.times[0],self.times[0]],self.times[::-1],[self.times[0]+pd.Timedelta(minutes=1)]]:
            with self.assertRaises(ValueError):hourly_index(times)

if __name__=='__main__':unittest.main(verbosity=2)
