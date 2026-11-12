"""Separate experiment entrypoint for C4a-calibrated fusion."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'C5'))
from run import main
if __name__=='__main__':
    sys.argv.extend(['--code','C5b'])
    main()
