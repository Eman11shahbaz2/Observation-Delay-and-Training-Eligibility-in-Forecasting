import gzip
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
import pandas as pd
from source_preparation import prepare_traffic,prepare_household,guarded_development_loader
from preflight_new_sources import sha
from audit_exports import write_union_csv_gz

class PreparationChecks(unittest.TestCase):
    def traffic(self,targets):
        n=len(targets)
        return pd.DataFrame(dict(date_time=['2020-01-01 00:00:00']*n,traffic_volume=targets,
            temp=['280']*n,rain_1h=['0']*n,snow_1h=['0']*n,clouds_all=['10']*n,
            weather_main=(['Clouds','Rain']*n)[:n]))

    def test_duplicate_traffic_target_consensus_never_sums_or_averages(self):
        self.assertEqual(prepare_traffic(self.traffic(['10','10'])).traffic_volume.iloc[0],10.)
        self.assertTrue(np.isnan(prepare_traffic(self.traffic(['10','11'])).traffic_volume.iloc[0]))
        self.assertTrue(np.isnan(prepare_traffic(self.traffic(['10','?'])).traffic_volume.iloc[0]))

    def test_traffic_covariate_conflicts_are_missing_and_category_order_is_invariant(self):
        raw=self.traffic(['10','10']);raw.loc[1,'temp']='281'
        first=prepare_traffic(raw);second=prepare_traffic(raw.iloc[::-1])
        self.assertTrue(np.isnan(first.temp.iloc[0]));pd.testing.assert_frame_equal(first,second)
        self.assertEqual(first.weather_main.iloc[0],'["Clouds","Rain"]')

    def household(self):
        return pd.DataFrame(dict(Date=['01/01/2020']*60,Time=[f'00:{n:02d}:00' for n in range(60)],
            Global_active_power=['1']*60,Global_reactive_power=['.2']*60,Voltage=['230']*60))

    def test_hourly_power_is_mean_kw_and_requires_all_sixty_finite_minutes(self):
        raw=self.household();raw.loc[0,'Global_active_power']='61'
        self.assertEqual(prepare_household(raw).Global_active_power.iloc[0],2.)
        raw.loc[0,'Global_active_power']='?'
        out=prepare_household(raw);self.assertTrue(np.isnan(out.Global_active_power.iloc[0]))
        self.assertEqual(out.Voltage.iloc[0],230.)

    def test_incomplete_or_duplicate_minutes_do_not_make_an_hour(self):
        raw=self.household()
        self.assertTrue(prepare_household(raw.iloc[:59]).iloc[0].isna().all())
        repeated=pd.concat([raw.iloc[:59],raw.iloc[[0]]],ignore_index=True)
        self.assertTrue(prepare_household(repeated).iloc[0].isna().all())

    def test_invalid_negative_or_fractional_traffic_targets_are_missing(self):
        for value in ['-1','1.5','inf']:
            self.assertTrue(np.isnan(prepare_traffic(self.traffic([value])).traffic_volume.iloc[0]))

    def test_guarded_loader_never_converts_reserved_numeric_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'source_archives').mkdir()
            raw=self.traffic(['10','10']);raw.loc[1,'date_time']='2020-01-01 01:00:00'
            raw.loc[1,'traffic_volume']='RESERVED_MUST_NOT_BE_PARSED'
            path=root/'source_archives/traffic_official.zip';member='Metro_Interstate_Traffic_Volume.csv.gz'
            with zipfile.ZipFile(path,'w') as z:z.writestr(member,gzip.compress(raw.to_csv(index=False).encode()))
            meta=dict(datasets=dict(traffic=dict(source_was_sorted=True,archive_sha256=sha(path),selected_member=member,
                development_source_timestamp_rows=1,reserved_source_timestamp_rows=1,
                plan=dict(start='2020-01-01 00:00:00',reserved_start='2020-01-01 01:00:00'))))
            (root/'TIMESTAMP_PREFLIGHT.json').write_text(json.dumps(meta))
            frame,audit=guarded_development_loader('traffic',root)
            self.assertEqual(frame.traffic_volume.iloc[0],10.);self.assertEqual(len(frame),1)
            self.assertEqual(audit['reserved_numeric_target_rows_parsed'],0)

class ExportChecks(unittest.TestCase):
    def test_two_dataset_schemas_are_unioned_in_one_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'snapshots.csv.gz'
            frames=[pd.DataFrame(dict(dataset=['traffic'],weather=['Rain'])),
                    pd.DataFrame(dict(dataset=['household'],Voltage=[230.]))]
            audit=write_union_csv_gz(frames,path)
            out=pd.read_csv(path);self.assertEqual(len(out),2)
            self.assertEqual(list(out),['dataset','weather','Voltage'])
            self.assertTrue(np.isnan(out.Voltage.iloc[0]));self.assertEqual(out.Voltage.iloc[1],230.)
            self.assertEqual(audit['compression'],'one gzip stream')
            with gzip.open(path,'rt') as stream:self.assertEqual(stream.read().count('dataset,weather,Voltage'),1)

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'file.csv.gz';path.write_bytes(b'ORIGINAL')
            bad=pd.DataFrame([[1,2]],columns=['duplicate','duplicate'])
            with self.assertRaises(ValueError):write_union_csv_gz([bad],path)
            self.assertEqual(path.read_bytes(),b'ORIGINAL')

if __name__=='__main__':unittest.main(verbosity=2)
