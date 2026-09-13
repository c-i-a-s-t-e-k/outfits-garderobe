"""Run only the tests affected by the files staged for commit.

Called by the pre-commit hook with the staged paths as arguments. A path inside
a Django app (or its `templates/<app>/` directory) selects that app's tests plus
the tests of every app that imports it, directly or transitively — outfits
builds on garments, garments on privatemedia — and always the cross-cutting
risk tests in the top-level `tests/`, which check every route's privacy
contract. Any other path (settings, conftest, `tests/` itself, shared
templates, dependencies) can affect every app, so it runs the whole suite.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RISK_TESTS = 'tests'


def discover_apps():
    return sorted(p.parent.name for p in ROOT.glob('*/tests') if p.is_dir())


def importers_of(apps):
    """Map each app to the apps whose code (tests included) imports it."""
    importers = {app: set() for app in apps}
    for app in apps:
        pattern = re.compile(rf'^\s*(from|import)\s+{app}\b', re.MULTILINE)
        for other in apps:
            if other == app:
                continue
            for path in (ROOT / other).rglob('*.py'):
                if 'migrations' not in path.parts and pattern.search(path.read_text()):
                    importers[app].add(other)
                    break
    return importers


def owning_app(path, apps):
    parts = Path(path).parts
    if len(parts) > 1 and parts[0] in apps:
        return parts[0]
    if len(parts) > 2 and parts[0] == 'templates' and parts[1] in apps:
        return parts[1]
    return None


def main(paths):
    apps = discover_apps()
    touched = {owning_app(path, apps) for path in paths}
    if None in touched:
        targets = []
    else:
        importers = importers_of(apps)
        targets = set()
        pending = list(touched)
        while pending:
            app = pending.pop()
            if app not in targets:
                targets.add(app)
                pending.extend(importers[app])
        targets = [*sorted(targets), RISK_TESTS]

    print(f'pytest: {" ".join(targets) if targets else "full suite"}', flush=True)
    return subprocess.call([sys.executable, '-m', 'pytest', '-q', *targets], cwd=ROOT)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
