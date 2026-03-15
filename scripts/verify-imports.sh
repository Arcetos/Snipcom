#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
echo "Verifying all module imports..."
python3 - <<'EOF'
import importlib, pkgutil, sys, pathlib

root = pathlib.Path("src")
sys.path.insert(0, str(root))

pkg = "snipcom_app"
failures = []
for finder, modname, ispkg in pkgutil.walk_packages(
        path=[str(root / pkg.replace(".", "/"))],
        prefix=pkg + "."):
    try:
        importlib.import_module(modname)
    except Exception as exc:
        failures.append(f"  FAIL {modname}: {exc}")

if failures:
    print("Import failures:")
    for f in failures:
        print(f)
    sys.exit(1)
print(f"All modules imported OK.")
EOF
