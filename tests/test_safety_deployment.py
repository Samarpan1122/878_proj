"""Exercise deployment ordering and argument construction without cloud access."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def environment(tmp_path, *, preflight_exit=0):
    data = tmp_path / 'data/safety'
    data.mkdir(parents=True)
    (data / 'snapshot.json').write_text('{}')
    log = tmp_path / 'commands.jsonl'
    gcloud = tmp_path / 'fake-gcloud'
    gcloud.write_text(f'#!{sys.executable}\nimport json,sys\nwith open({str(log)!r}, "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
    gcloud.chmod(0o700)
    python = tmp_path / 'fake-python'
    python.write_text(f'#!/bin/sh\nexit {preflight_exit}\n')
    python.chmod(0o700)
    env = {**os.environ, 'GCLOUD_BIN': str(gcloud), 'PYTHON_BIN': str(python),
           'SKIP_BUILD': 'true', 'DATA_BUCKET': 'test-bucket', 'SKIP_DATA_UPLOAD': 'true',
           'ENABLE_SCHEDULES': 'false', 'PUBLIC_DEMO': 'false'}
    for key in ('CLOUD_SQL_CONNECTION', 'DATABASE_SECRET'):
        env.pop(key, None)
    return env, log


def test_technical_failure_stops_before_any_cloud_command(tmp_path):
    env, log = environment(tmp_path, preflight_exit=1)
    result = subprocess.run(['bash', str(ROOT / 'infra/cloud-run.sh'), 'test-project'], cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode != 0
    assert not log.exists()


def test_code_only_deployment_preserves_data_and_private_access(tmp_path):
    env, log = environment(tmp_path)
    result = subprocess.run(['bash', str(ROOT / 'infra/cloud-run.sh'), 'test-project'], cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(call[:2] == ['storage', 'cp'] for call in calls)
    deploy = next(call for call in calls if call[:2] == ['run', 'deploy'])
    assert '--no-allow-unauthenticated' in deploy
    assert any(flag.startswith('--startup-probe=httpGet.path=/ready,') for flag in deploy)
    assert any(flag.startswith('--update-env-vars=') for flag in deploy)
    assert any('readonly=true' in flag for flag in deploy)


def test_rollback_validates_revision_before_traffic_change(tmp_path):
    env, log = environment(tmp_path)
    bad = subprocess.run(['bash', str(ROOT / 'infra/rollback-cloud-run.sh'), 'test-project', 'other-service-00001'], cwd=tmp_path, env=env, capture_output=True)
    assert bad.returncode != 0 and not log.exists()
    good = subprocess.run(['bash', str(ROOT / 'infra/rollback-cloud-run.sh'), 'test-project', 'geocrash-safety-00001-test'], cwd=tmp_path, env=env, capture_output=True)
    assert good.returncode == 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[0][:3] == ['run', 'revisions', 'describe']
    assert calls[1][:3] == ['run', 'services', 'update-traffic']
    assert '--to-revisions=geocrash-safety-00001-test=100' in calls[1]
    assert len(calls) == 2
