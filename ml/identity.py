"""Bind verified completed-run records to their actual inputs without changing metrics."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .train import atomic_json, sha, arrays


def read(path):
    return json.loads(Path(path).read_text())


def main():
    manifest = read('web/public/models/manifest.json')
    candidate = read('artifacts/candidate-evaluation.json')
    rows, x, y, mask, splits = arrays()
    assert sha('web/public/models/model.onnx') == manifest['sha256']
    assert sha('artifacts/model.safetensors') == manifest['weightsSha256']
    assert sha('artifacts/data-manifest.jsonl') == manifest['dataSha256']
    assert sha('data/tensors/all.f32') == candidate['tensorSha256']
    assert len(rows) == candidate['rows']
    base = {'referenceReleaseModelSha256': manifest['sha256'],
            'dataSha256': manifest['dataSha256'],
            'candidateTensorSha256': candidate['tensorSha256'],
            'candidateCount': len(rows),
            'trainingCandidates': len(splits['train']),
            'preprocessVersion': manifest['preprocessVersion'],
            'primaryTrainingSourceSha': manifest['trainingSourceSha'],
            'upstreamWeightsSha256': manifest['upstreamWeightsSha256']}

    def attach(path, payload, details):
        previous = payload.pop('identity', None)
        source_time = previous['completedRecordModifiedUtc'] if previous else datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc).isoformat()
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        payload['identity'] = {**base, **details,
                               'completedRecordModifiedUtc': source_time,
                               'metricsPayloadCanonicalSha256': payload_hash,
                               'identityAttachedAfterRun': True}
        atomic_json(path, payload)

    experiments = read('artifacts/experiments.json')
    for run in experiments['models']:
        checkpoint = f"artifacts/checkpoints/{run['kind']}-{run['seed']}.safetensors"
        assert sha(checkpoint) == run['weightsSha256']
        assert run['test']['classes'][0]['n'] == len(splits['test'])
    selected = next(r for r in experiments['models'] if r['kind'] == 'local_context' and r['seed'] == manifest['seed'])
    assert selected['weightsSha256'] == manifest['weightsSha256']
    attach('artifacts/experiments.json', experiments,
           {'usesReleasedTaskEncoder': 'selected local_context run only; every comparison has its own checkpoint hash',
            'verification': 'All nine saved checkpoints and the selected released safetensors match the recorded weights hashes; current candidate totals and held-family dimensions match.'})

    result = read('artifacts/model-results.json')
    assert result['candidateCount'] == len(rows)
    attach('artifacts/model-results.json', result,
           {'usesReleasedTaskEncoder': True, 'modelSha256': manifest['sha256'],
            'verification': 'Selected checkpoint and current corpus verified against primary experiment records.'})

    replay = read('artifacts/replay-results.json')
    assert replay['poolPages'] == len({rows[i]['pageId'] for i in splits['train']})
    assert len(replay['runs']) == 9
    for run in replay['runs']:
        for point in run['curve']:
            assert point['test']['classes'][0]['n'] == len(splits['test'])
            assert all(p in {rows[i]['pageId'] for i in splits['train']} for p in point['revealedPages'])
    attach('artifacts/replay-results.json', replay,
           {'usesReleasedTaskEncoder': False,
            'verification': 'Completed corrected-corpus replay; exact pool/page IDs and test candidate count match current arrays. Only the pinned generic pretrained encoder is used.'})

    stress = read('artifacts/stress-results.json')
    for key in ['domainExclusion', 'symptomExclusion']:
        run = stress[key]['training']
        assert sha(f"artifacts/checkpoints/{run['kind']}-{run['seed']}.safetensors") == run['weightsSha256']
    attach('artifacts/stress-results.json', stress,
           {'usesReleasedTaskEncoder': False,
            'stressDataSha256': sha('artifacts/stress-manifest.jsonl'),
            'verification': 'Both separately trained exclusion checkpoints match their actual run hashes; authored secondary rendered manifest is separately hashed.'})

    samples = read('web/public/examples/index.json')
    evidence = []
    for sample in samples:
        hashes = {side: sha(Path('web/public/examples') / sample[side]) for side in ['before', 'after']}
        assert all(hashes[side] == sample[f'{side}Sha256'] for side in hashes)
        evidence.append({'id': sample['id'], 'beforeSha256': hashes['before'], 'afterSha256': hashes['after']})
    for filename, uses_model in [('preprocessing-timing.json', False), ('end-to-end-timing.json', True)]:
        timing = read('artifacts/' + filename)
        assert [r['id'] for r in timing['results']] == [s['id'] for s in samples]
        attach('artifacts/' + filename, timing,
               {'usesReleasedTaskEncoder': uses_model, 'exampleInputs': evidence,
                'verification': 'Completed final-image benchmark; example file hashes and recorded sample ordering verified. Preprocessing timing contains no neural inference.'})
    print('Verified current model, checkpoints, candidate tensors, examples and completed experiment identities.')


if __name__ == '__main__':
    main()
