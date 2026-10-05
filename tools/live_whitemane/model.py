"""Run the retained archaeology Laya head on a separate live-trial loopback port."""
import argparse
from pathlib import Path
from tools.client_compatibility import archaeology_model_service as service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8004)
    parser.add_argument('--adapter', type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError('invalid loopback port')
    service.PORT = args.port
    service.serve(args.adapter)


if __name__ == '__main__':
    main()
