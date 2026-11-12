"""C1 fixed raw indoor baseline and fixed image correspondences."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import baseline


def main():
    data=c.load_data('tum-freiburg1_desk')
    stage=c.Stage('C1',data['dataset'],parents=[data['parent']])
    try:
        matches,metrics=baseline.prepare(stage,data,stage.path/'artifacts/baseline')
        stage.finish(metrics,baseline.report_text(stage,metrics))
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
