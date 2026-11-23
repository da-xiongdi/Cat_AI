"""Validate a research configuration without training or scoring."""
import argparse
import json
from pathlib import Path

from catalyst_ai.modeling.research_preflight import preflight

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    result = preflight(args.config, root=ROOT)
    print(json.dumps({'result': 'passed', 'counts': result['counts'], 'hashes': result['hashes'],
                      'config': result['config']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
