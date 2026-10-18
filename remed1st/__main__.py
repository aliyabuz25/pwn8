import argparse
import json
from .device import probe


def main():
    p = argparse.ArgumentParser(description='remed1st — GTK iPhone device monitor')
    p.add_argument('--probe-json', action='store_true', help='Read device information without GTK')
    p.add_argument('--smoke-test', type=int, default=0, metavar='SECONDS')
    args = p.parse_args()
    if args.probe_json:
        print(json.dumps(probe().to_dict(), ensure_ascii=False, indent=2))
        return 0
    try:
        from .app import RemedApp
    except (ImportError, ValueError) as e:
        p.exit(1, f'GTK4/PyGObject was not found: {e}\nmacOS: brew install gtk4 pygobject3\n')
    app = RemedApp(args.smoke_test)
    code = app.run(['remed1st'])
    return (0 if app.smoke_passed else 1) if args.smoke_test else code


if __name__ == '__main__':
    raise SystemExit(main())
