import base64
import copy
import io
import json
import subprocess
import sys
import threading

import pytest
from PIL import Image, ImageDraw

from server.analysis import ROOT, node_command, run_analysis
from server.gate import evaluate_gate
from server.reports import report_html, report_json
from server.store import Store


@pytest.fixture(scope='module')
def reports(tmp_path_factory):
    folder = tmp_path_factory.mktemp('gate-reports')
    store = Store(folder)
    project = store.create_project('Gate regression')
    before = Image.new('RGB', (128, 96), 'white')
    after = before.copy()
    ImageDraw.Draw(after).rectangle((20, 20, 70, 60), fill='#245040')

    def png(image):
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()

    result = {}
    for name, current in [('unchanged', before), ('unreviewed', after)]:
        job = store.create_job(project['id'], 'import')
        run_analysis(store, job, {'before': png(before), 'after': png(current)}, threading.Event())
        state = store.job(job['id'])
        assert state['status'] == 'complete', state
        result[name] = report_json(store.run(state['runId']), folder / 'runs' / state['runId'])
    result['violated'] = json.loads((ROOT / 'examples/main/report.json').read_text())
    result['intentional'] = json.loads((ROOT / 'examples/intentional/report.json').read_text())
    result['inconclusive'] = json.loads((ROOT / 'examples/failure/report.json').read_text())
    return result


def cases(reports):
    values = [('minimal missing evidence', {'execution': 'complete'}, 3), ('null root', None, 3), ('array root', [], 3)]
    for name, expected in [('unchanged', 0), ('unreviewed', 1), ('violated', 2), ('intentional', 0), ('inconclusive', 3)]:
        values.append((name, copy.deepcopy(reports[name]), expected))
    for field in ['analysis', 'predictions', 'model', 'decisions']:
        run = copy.deepcopy(reports['unreviewed'])
        del run[field]
        values.append(('missing ' + field, run, 3))
    for field in ['candidates', 'width', 'height', 'heightDelta', 'changedPixels', 'mode', 'version']:
        run = copy.deepcopy(reports['unchanged'])
        del run['analysis'][field]
        values.append(('missing analysis ' + field, run, 3))
    for state in ['error', 'cancelled', 'incomparable', 'unknown']:
        run = copy.deepcopy(reports['violated'])
        run['execution'] = state
        values.append(('execution ' + state, run, 3))
    for state in ['unknown', 'unchecked', None, [], {}]:
        run = copy.deepcopy(reports['intentional'])
        run['contracts'][0]['status'] = state
        values.append(('contract status ' + str(state), run, 3))
    for field, value in [('schemaVersion', '2.0'), ('reportSchema', 'other/1'), ('model', {}), ('predictions', []), ('decisions', []), ('contracts', {}), ('analysis', None)]:
        run = copy.deepcopy(reports['unreviewed'])
        run[field] = value
        values.append(('invalid ' + field, run, 3))
    run = copy.deepcopy(reports['intentional'])
    del run['contracts']
    values.append(('missing declared contract results', run, 3))
    run = copy.deepcopy(reports['unreviewed'])
    del run['contracts']
    values.append(('no declared contracts', run, 1))
    for field in ['images', 'beforeUrl', 'afterUrl', 'gate']:
        run = copy.deepcopy(reports['unchanged'])
        run.pop(field, None)
        values.append(('optional ' + field, run, 0))
    for name, mutate in [
        ('missing candidate pixel count', lambda r: r['analysis']['candidates'][0].pop('changedPixels')),
        ('missing candidate id', lambda r: r['analysis']['candidates'][0].pop('id')),
        ('duplicate candidate id', lambda r: r['analysis']['candidates'].append(copy.deepcopy(r['analysis']['candidates'][0]))),
        ('unknown prediction id', lambda r: r['predictions'][0].update(candidateId='absent')),
        ('duplicate prediction', lambda r: r['predictions'].append(copy.deepcopy(r['predictions'][0]))),
        ('missing logits', lambda r: r['predictions'][0].pop('logits')),
        ('invalid scores', lambda r: r['predictions'][0].update(scores=[2] * 5)),
        ('unknown review target', lambda r: r['decisions'].update(absent={'decision': 'intentional_change'})),
        ('unknown review decision', lambda r: r['decisions'].update({r['analysis']['candidates'][0]['id']: {'decision': 'approved'}})),
        ('invalid review', lambda r: r['decisions'].update({r['analysis']['candidates'][0]['id']: None})),
    ]:
        run = copy.deepcopy(reports['unreviewed'])
        mutate(run)
        values.append((name, run, 3))
    for decision, expected in [('intentional_change', 0), ('confirm_defect', 2), ('uncertain', 1), ('unreviewed', 1)]:
        run = copy.deepcopy(reports['unreviewed'])
        run['decisions'] = {c['id']: {'decision': decision} for c in run['analysis']['candidates']}
        values.append(('review ' + decision, run, expected))
    run = copy.deepcopy(reports['violated'])
    run.pop('predictions')
    values.append(('missing evidence precedes violation', run, 3))
    for name, mutate in [
        ('conflicting captured status', lambda r: r['capture']['contracts'][0].update(status='violated')),
        ('missing measurements', lambda r: r['contracts'][0].update(measurements=[None])),
        ('unknown nested status', lambda r: r['contracts'][0]['after'].update(status='unknown')),
        ('missing side results', lambda r: r['capture']['after'].pop('contracts')),
        ('foreign review history', lambda r: r['events'][0].update(runId='another-run')),
    ]:
        run = copy.deepcopy(reports['intentional'])
        mutate(run)
        values.append((name, run, 3))
    run = copy.deepcopy(reports['intentional'])
    def remove_related(value):
        if isinstance(value, dict):
            if value.get('type') == 'inside-container' and 'measurements' in value:
                value['measurements'] = value['measurements'][:1]
            for child in value.values():
                remove_related(child)
        elif isinstance(value, list):
            for child in value:
                remove_related(child)
    remove_related(run)
    values.append(('missing related measurement', run, 3))
    run = copy.deepcopy(reports['unreviewed'])
    run.pop('schemaVersion')
    run['reportSchema'] = 'renderguard-report/1'
    values.append(('browser exported format', run, 1))
    run = copy.deepcopy(reports['unreviewed'])
    run.pop('schemaVersion')
    run['source'] = 'browser PNG import'
    values.append(('existing browser storage format', run, 1))
    return values


def test_gate_validates_actual_analysis_reports(reports):
    failures = []
    for name, run, code in cases(reports):
        try:
            result = evaluate_gate(run)
            if result['code'] != code:
                failures.append(f'{name}: expected {code}, got {result}')
        except (AttributeError, TypeError, KeyError) as error:
            failures.append(f'{name}: {type(error).__name__}')
    assert not failures, '\n'.join(failures)


def test_python_browser_gate_parity(reports):
    entries = cases(reports)
    process = subprocess.run(node_command('tests/gate-evaluate.ts'), input=json.dumps([r for _, r, _ in entries]), text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert process.returncode == 0, process.stderr
    for (name, run, code), result in zip(entries, json.loads(process.stdout), strict=True):
        assert result == evaluate_gate(run), name
        assert result['code'] == code, name


@pytest.mark.parametrize('content', ['{"execution":"complete"}', 'null', '[]', '{broken'])
def test_gate_cli_rejects_invalid_input_without_traceback(tmp_path, content):
    path = tmp_path / 'report.json'
    path.write_text(content)
    process = subprocess.run([sys.executable, '-m', 'server.gate', str(path)], cwd=ROOT, text=True, capture_output=True)
    assert process.returncode == 3
    assert json.loads(process.stdout)['code'] == 3
    assert process.stderr == ''


def test_gate_cli_valid_reports_and_fresh_exports(tmp_path, reports):
    for name, run, expected in cases(reports):
        if not isinstance(run, dict) or name not in reports:
            continue
        run['gate'] = {'code': 0, 'reason': 'Outdated result'}
        exported = report_json(run, tmp_path)
        assert exported['gate']['code'] == expected
        assert f'Gate: {expected}' in report_html(run, tmp_path)
        path = tmp_path / 'report.json'
        path.write_text(json.dumps(exported))
        process = subprocess.run([sys.executable, '-m', 'server.gate', str(path)], cwd=ROOT, text=True, capture_output=True)
        assert process.returncode == expected, (name, process.stdout, process.stderr)
        assert json.loads(process.stdout)['code'] == expected
        assert process.stderr == ''


def test_browser_exports_use_current_gate(reports):
    entries = [(name, run, code) for name, run, code in cases(reports) if isinstance(run, dict)]
    for _, run, _ in entries:
        run['gate'] = {'code': 0, 'reason': 'Outdated result'}
    process = subprocess.run(node_command('tests/gate-evaluate.ts') + ['--exports'], input=json.dumps([r for _, r, _ in entries]), text=True, capture_output=True, cwd=ROOT, timeout=30)
    assert process.returncode == 0, process.stderr
    for (name, run, code), result in zip(entries, json.loads(process.stdout), strict=True):
        assert result['json']['code'] == code, name
        assert f'Gate {code}' in result['html'], name
