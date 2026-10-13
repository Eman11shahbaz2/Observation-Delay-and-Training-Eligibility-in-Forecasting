"""Package validated evidence, excluding redundant checkpoints and temporary files."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent / 'Reporting_Delay_Completed_Study.zip'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    validation = json.loads((ROOT / 'VALIDATION_RESULTS.json').read_text())
    assert validation['checks_passed'] == 83 and validation['checks_failed'] == 0
    for name, digest in validation['validated_evidence_sha256'].items():
        assert sha(ROOT / name) == digest, name
    files = sorted(p for p in ROOT.rglob('*') if p.is_file()
                   and '__pycache__' not in p.parts and 'checkpoints' not in p.parts
                   and not p.name.endswith('.tmp') and p.name != 'CHECKSUMS.sha256')
    assert (ROOT / 'COMPLETED_STUDY_REPORT.md') in files
    identities = {str(p.relative_to(ROOT)): sha(p) for p in files}
    checksums = ROOT / 'CHECKSUMS.sha256'
    checksums.write_text(''.join(f'{digest}  {name}\n' for name, digest in identities.items()))
    with zipfile.ZipFile(DEST, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files + [checksums]:
            archive.write(path, str(path.relative_to(ROOT)))
    with zipfile.ZipFile(DEST) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(identities) + 1
        for name, digest in identities.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest, name
    print(json.dumps(dict(path=str(DEST), file_count=len(identities) + 1,
                         size_bytes=DEST.stat().st_size, sha256=sha(DEST)), indent=2))

if __name__ == '__main__':
    main()
