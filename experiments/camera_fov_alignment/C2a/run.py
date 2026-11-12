"""Explicitly exploratory coefficient fit with original low-support indoor tracks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fit import run_indoor
if __name__=='__main__':run_indoor('C2a',1,diagnostic=True)
