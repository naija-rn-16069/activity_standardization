"""
Convenience wrapper: run normalization after ensuring dependencies.
Usage:
  python scripts/run_normalization.py
"""
import subprocess, sys

REQUIRED = ['pandas', 'pyyaml']

def ensure_deps():
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            print(f'Installing {pkg}...')
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])

def main():
    ensure_deps()
    subprocess.check_call([sys.executable, 'scripts/normalize_cloud_activity.py'])

if __name__ == '__main__':
    main()