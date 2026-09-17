"""Install a locally reviewed recording-specific resource; never distribute game assets."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lmu_data_analysis.storage import SQLiteSessionRepository, LocalBlobStore
from lmu_data_analysis.web_app import LOCAL_DRIVER_ID
from lmu_data_analysis.reader import read_recording
from lmu_data_analysis.track_reference import validate_resource


def install(data_dir, session_id, resource_path):
    repository = SQLiteSessionRepository(data_dir / 'catalog.sqlite3')
    session = repository.get_session(LOCAL_DRIVER_ID, session_id)
    if session is None:
        raise ValueError('练习不存在')
    if resource_path.stat().st_size > 10*1024*1024:
        raise ValueError('资源超过 10 MB')
    resource = json.loads(resource_path.read_text(encoding='utf-8'))
    with LocalBlobStore(data_dir / 'recordings').materialize(session['blob_key']) as path:
        result = validate_resource(resource, read_recording(path))
    folder = data_dir / 'track-resources'
    folder.mkdir(exist_ok=True)
    key = uuid4().hex
    target = folder / (key+'.json')
    target.write_text(json.dumps(resource, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    try:
        with repository.connection() as c:
            c.execute('INSERT INTO track_references VALUES (?,?) ON CONFLICT(session_id) '
                      'DO UPDATE SET resource_key=excluded.resource_key', (session_id, key))
    except Exception:
        target.unlink()
        raise
    return {k: result[k] for k in ('validation_status','max_error_m','rms_error_m')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='接入已人工核验的赛道资源')
    parser.add_argument('session_id')
    parser.add_argument('resource', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    print(json.dumps(install(args.data_dir, args.session_id, args.resource), ensure_ascii=False))
