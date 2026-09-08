"""Create portable experiment and generated-scene archives with deterministic entries."""
import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def archive(destination, paths):
    with destination.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as stream:
        for path in sorted(set(paths)):
            if not path.is_file():
                continue
            item = stream.gettarinfo(str(path), arcname=str(path.relative_to(ROOT)))
            item.uid = item.gid = 0
            item.uname = item.gname = ''
            item.mtime = 0
            with path.open('rb') as content:
                stream.addfile(item, content)
    return {'file': destination.name, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'bytes': destination.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = list((ROOT / 'data').glob('*.png'))
    data += [ROOT / 'artifacts' / name for name in ['data-manifest.jsonl', 'groups.json', 'generation.json']]
    experiments = [path for path in (ROOT / 'artifacts').rglob('*') if path.is_file() and path.suffix in ('.json', '.jsonl', '.npz', '.safetensors', '.log') and not path.name.startswith('pilot-')]
    models = [path for path in (ROOT / 'web/public/models').iterdir() if path.is_file()]
    models += [ROOT / 'artifacts' / name for name in ['model.safetensors', 'replay-buffer.npz', 'replay-buffer.json', 'training-config.json', 'MODEL-LICENSE']]
    results = [archive(args.output / 'renderguard-scenes.tar.gz', data), archive(args.output / 'renderguard-experiments.tar.gz', experiments), archive(args.output / 'renderguard-model.tar.gz', models)]
    (args.output / 'artifact-index.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
