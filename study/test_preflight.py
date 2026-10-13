import unittest
import numpy as np
import pandas as pd
from preflight_new_sources import read_timestamp_bytes,structural_audit,household_complete_hours,gap_summary

class TimestampChecks(unittest.TestCase):
    def test_traffic_target_values_are_not_parsed(self):
        a=b'date_time,traffic_volume,temp\n2020-01-01 00:00:00,DO_NOT_PARSE,OTHER\n2020-01-01 01:00:00,DO_NOT_PARSE,OTHER\n'
        b=a.replace(b'DO_NOT_PARSE',b'COMPLETELY_DIFFERENT')
        first,headers=read_timestamp_bytes(a,'traffic');second,_=read_timestamp_bytes(b,'traffic')
        np.testing.assert_array_equal(first,second)
        self.assertIn('traffic_volume',headers)
        self.assertEqual(structural_audit(first,'traffic'),structural_audit(second,'traffic'))

    def test_household_measurement_values_are_not_parsed(self):
        data=b'Date;Time;Global_active_power;Voltage\n01/02/2020;00:00:00;DO_NOT_PARSE;DO_NOT_PARSE\n01/02/2020;00:01:00;DO_NOT_PARSE;DO_NOT_PARSE\n'
        index,headers=read_timestamp_bytes(data,'household')
        self.assertEqual(index[0],pd.Timestamp('2020-02-01'))
        self.assertEqual(len(index),2);self.assertIn('Global_active_power',headers)

    def test_hourly_and_minutely_resolution_enforced(self):
        for data,name in [(b'date_time\n2020-01-01 00:01:00\n','traffic'),
            (b'Date;Time\n01/01/2020;00:00:01\n','household')]:
            with self.assertRaises(ValueError):read_timestamp_bytes(data,name)

    def test_malformed_dates_are_rejected(self):
        with self.assertRaises(ValueError):read_timestamp_bytes(b'date_time\nNOT_A_DATE\n','traffic')

    def test_duplicate_traffic_timestamp_counts_and_gap_are_independent(self):
        index=pd.DatetimeIndex(['2020-01-01 00:00','2020-01-01 00:00','2020-01-01 03:00'])
        report=structural_audit(index,'traffic')
        self.assertEqual(report['duplicate_extra_rows'],1);self.assertEqual(report['duplicate_timestamp_groups'],1)
        self.assertEqual(report['missing_clock_hours'],2);self.assertEqual(report['largest_missing_run_steps'],2)

    def test_household_complete_hour_requires_sixty_distinct_stamps(self):
        first=pd.date_range('2020-01-01',periods=60,freq='min')
        incomplete=pd.date_range('2020-01-01 01:00',periods=59,freq='min')
        duplicate=pd.date_range('2020-01-01 02:00',periods=59,freq='min').append(pd.DatetimeIndex(['2020-01-01 02:00']))
        complete,counts,bad=household_complete_hours(first.append(incomplete).append(duplicate))
        np.testing.assert_array_equal(complete,pd.DatetimeIndex(['2020-01-01']))
        self.assertEqual(counts.iloc[2],60);self.assertEqual(len(bad),1)

    def test_structural_counts_do_not_claim_numeric_feasibility(self):
        report=structural_audit(pd.date_range('2020-01-01',periods=2000,freq='h'),'traffic')
        self.assertEqual(len(report['potential_case_counts']),8)
        self.assertTrue(all(not row['numeric_feasibility_verified'] for row in report['potential_case_counts']))
        self.assertEqual(report['plan']['development'][-1]['future_end'],report['plan']['reserved_start'])

    def test_missing_forecast_origin_does_not_remove_present_future_target(self):
        index=pd.date_range('2020-01-01',periods=2000,freq='h')
        first=structural_audit(index,'traffic')['potential_case_counts']
        # A missing origin at 1200 still has its target at 1206; the absent target at 1200
        # belongs to historical origin 1194, not future origin 1200.
        second=structural_audit(index.delete(1200),'traffic')['potential_case_counts']
        for a,b in zip(first[:4],second[:4]):self.assertEqual(a['potential_future_n'],b['potential_future_n'])

if __name__=='__main__':unittest.main(verbosity=2)
