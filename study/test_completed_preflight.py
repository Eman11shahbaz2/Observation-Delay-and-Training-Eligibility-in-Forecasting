import json
from pathlib import Path
import unittest
import pandas as pd
from preflight_new_sources import sha,read_archive

ROOT=Path(__file__).resolve().parent

class CompletedPreflightChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'TIMESTAMP_PREFLIGHT.json').read_text())

    def test_no_outcome_analysis_and_current_audit_hashes(self):
        r=self.report
        self.assertEqual(r['models_fitted'],0);self.assertEqual(r['scores_computed'],0)
        for k in ['target_columns_loaded_for_analysis','measurement_columns_loaded_for_analysis','target_missingness_profiled']:
            self.assertFalse(r[k])
        self.assertEqual(r['script_sha256'],sha(ROOT/'preflight_new_sources.py'))
        self.assertEqual(r['audit_rules_sha256'],sha(ROOT/'AUDIT_RULES.md'))
        self.assertEqual(r['replay_core_sha256'],sha(ROOT/'replay_core.py'))

    def test_archive_timestamp_counts_and_members_recompute(self):
        for name,d in self.report['datasets'].items():
            path=ROOT/'source_archives'/f'{name}_official.zip'
            self.assertEqual(sha(path),d['archive_sha256'])
            index,headers,member=read_archive(path,name)
            self.assertEqual(len(index),d['source_rows']);self.assertEqual(len(index.unique()),d['unique_timestamps'])
            self.assertEqual(int(index.duplicated().sum()),d['duplicate_extra_rows'])
            self.assertEqual(headers,d['header_names'])
            for k,v in member.items():self.assertEqual(v,d[k])
            cut=pd.Timestamp(d['plan']['reserved_start'])
            self.assertEqual(int((index<cut).sum()),d['development_source_timestamp_rows'])
            self.assertEqual(int((index>=cut).sum()),d['reserved_source_timestamp_rows'])

    def test_all_sixteen_potential_cases_are_explicitly_not_numeric_feasibility(self):
        cases=[r for d in self.report['datasets'].values() for r in d['potential_case_counts']]
        self.assertEqual(len(cases),16)
        for r in cases:
            self.assertTrue(r['timestamp_count_gates_pass']);self.assertFalse(r['numeric_feasibility_verified'])
            self.assertGreaterEqual(r['potential_inner_train_n'],500)
            self.assertGreaterEqual(r['potential_inner_validation_n'],100)
            self.assertGreaterEqual(r['potential_future_n'],100)

    def test_primary_pair_counts_and_all_future_counts_match(self):
        for name,d in self.report['datasets'].items():
            for period in ['T1','T2']:
                g=[r for r in d['potential_case_counts'] if r['period']==period]
                self.assertEqual(len({r['potential_future_n'] for r in g}),1)
                a=next(r for r in g if (r['O'],r['L'])==(0,24))
                b=next(r for r in g if (r['O'],r['L'])==(24,0))
                for k in ['potential_inner_train_n','potential_inner_validation_n','potential_common_history_n','potential_future_n']:
                    self.assertEqual(a[k],b[k])
            self.assertEqual(d['plan']['development'][-1]['future_end'],d['plan']['reserved_start'])

if __name__=='__main__':unittest.main(verbosity=2)
