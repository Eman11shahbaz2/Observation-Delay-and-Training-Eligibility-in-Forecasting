import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
import pandas as pd
import expansion_api as api
import source_preparation as prep
from preflight_new_sources import sha

class ExpansionExecutionChecks(unittest.TestCase):
    def frame(self,name):
        index=pd.date_range('2020-01-01',periods=300,freq='h')
        cfg=api.CONFIG[name]
        frame=pd.DataFrame({cfg['target']:np.arange(300,dtype=float)},index=index)
        for col in cfg['numeric']:frame[col]=np.arange(300,dtype=float)+1
        for col in cfg['categorical']:frame[col]='["Rain"]'
        return frame

    def test_source_configs_equal_frozen_ledger(self):
        root=Path(__file__).resolve().parent
        source=json.loads((root/'SOURCE_CONFIG.json').read_text())
        for name,cfg in api.CONFIG.items():
            frozen=source['datasets'][name]
            self.assertEqual(cfg['target'],frozen['target'])
            self.assertEqual(cfg['numeric'],frozen['numeric_covariates'])
            self.assertEqual(cfg['categorical'],frozen['categorical_covariates'])

    def test_new_source_features_follow_original_timing_roles(self):
        for name in api.CONFIG:
            frame=self.frame(name)
            for o in (0,24):
                x,p,used=api.build_features(frame,name,o)
                self.assertEqual(x.iloc[250].target_lag_1,249-o)
                self.assertEqual(p[250],249-o);self.assertEqual(used[250],frame.index[249-o])
                for col in api.CONFIG[name]['numeric']:self.assertEqual(x.iloc[250]['observed_'+col],250.)
                self.assertEqual(len(x.columns),5+6+len(api.CONFIG[name]['numeric'])+len(api.CONFIG[name]['categorical']))

    def test_unavailable_values_cannot_change_new_source_snapshots(self):
        for name,cfg in api.CONFIG.items():
            frame=self.frame(name);x,p,_=api.build_features(frame,name,24)
            frame.loc[frame.index[226]:,cfg['target']]=-999
            changed,q,_=api.build_features(frame,name,24)
            pd.testing.assert_series_equal(x.iloc[250],changed.iloc[250]);self.assertEqual(p[250],q[250])

    def test_household_guard_prevents_numeric_conversion_of_reserved_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'source_archives').mkdir()
            times=pd.date_range('2020-01-01',periods=120,freq='min')
            raw=pd.DataFrame(dict(Date=times.strftime('%d/%m/%Y'),Time=times.strftime('%H:%M:%S'),
                Global_active_power=['1']*60+['RESERVED_POISON']*60,
                Global_reactive_power=['.2']*120,Voltage=['230']*120))
            path=root/'source_archives/household_official.zip';member='household_power_consumption.txt'
            with zipfile.ZipFile(path,'w') as z:z.writestr(member,raw.to_csv(index=False,sep=';'))
            meta=dict(datasets=dict(household=dict(source_was_sorted=True,archive_sha256=sha(path),selected_member=member,
                development_source_timestamp_rows=60,reserved_source_timestamp_rows=60,
                plan=dict(start='2020-01-01 00:00:00',reserved_start='2020-01-01 01:00:00'))))
            (root/'TIMESTAMP_PREFLIGHT.json').write_text(json.dumps(meta))
            original=prep.finite_numeric
            def reject_poison(values):
                if values.astype(str).str.contains('RESERVED_POISON').any():raise AssertionError('Reserved value reached numeric conversion.')
                return original(values)
            with patch.object(prep,'finite_numeric',side_effect=reject_poison):frame,audit=prep.guarded_development_loader('household',root)
            self.assertEqual(frame.Global_active_power.iloc[0],1.);self.assertEqual(len(frame),1)
            self.assertEqual(audit['reserved_numeric_target_rows_parsed'],0)

if __name__=='__main__':unittest.main(verbosity=2)
