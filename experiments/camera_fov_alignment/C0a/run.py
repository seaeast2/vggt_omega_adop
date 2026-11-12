"""Auxiliary audit: reject inexact KD search; select exact BF secondary metric."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import cv2
import numpy as np


def main():
    stage=c.Stage('C0a',extra={'reason':'C0-001 nearest-neighbor backend audit failure'})
    try:
        rng=np.random.default_rng(0)
        rng.uniform(c.LOW,c.HIGH,(3,2));rng.uniform([-1.2,-.9,3.],[1.2,.9,7.],(180,3))
        rng.normal(0,.3,(600,3,6));rng.normal(0,.0003,(600,3));rng.normal(0,.15,(30,3))
        target=rng.normal(size=(250,3)).astype(np.float32)
        query=rng.normal(size=(40,3)).astype(np.float32)
        exact=((query[:,None,:]-target[None,:,:])**2).sum(2)
        cv2.setRNGSeed(0)
        tree=cv2.flann_Index(target,dict(algorithm=1,trees=1))
        ix,dist=tree.knnSearch(query,1,params=dict(checks=-1,eps=0.,sorted=True))
        wrong=int((ix[:,0]!=exact.argmin(1)).sum())
        bf=cv2.BFMatcher(cv2.NORM_L2)
        out=bf.match(query,target)
        corrected=np.array([m.trainIdx for m in out])
        assert np.array_equal(corrected,exact.argmin(1))
        assert np.allclose(np.array([m.distance**2 for m in out]),exact.min(1),rtol=2e-6,atol=1e-6)
        result={'decision':'TECHNICAL_PASS','flann_wrong_neighbors':wrong,
            'flann_squared_distance_error_max':float(np.max(np.abs(dist[:,0]-exact.min(1)))),
            'replacement':'exact float32 BFMatcher L2, 512 fixed query points per frame against full target frame',
            'replacement_vs_numpy_exhaustive':'passed','scientific_improvement':False}
        stage.finish(result,f'''# C0a 최근접점 검색 보조 검증

**TECHNICAL_PASS**. C0 최초 실패를 보존하고 원인을 확인했다.

- seed 0, KD-tree 1개, checks=-1에서 exhaustive 정답과 다른 이웃: {wrong}/40.
- 정확한 float32 L2 brute-force 방식으로 대체하고 NumPy 전체 거리 대조 통과.
- 조밀 점군 보조 지표는 프레임별 고정 512개 query와 상대 프레임 전체 target을 사용한다. 전체 source 점의 통계로 부르지 않는다.
- FoV fit은 고정 대응의 float64 affine residual이며 이 검색 방식의 영향을 받지 않는다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
