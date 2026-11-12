"""Synthetic camera/scene observability and insufficient-support controls."""
import itertools
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import matching
import cv2
import numpy as np


def main():
    stage=c.Stage('C0b')
    try:
        rng=np.random.default_rng(13);results=[]
        world=rng.uniform([-1.,-.8,3.],[1.,.8,6.],(100,3))
        k=np.repeat(np.array([[[420.,0,256.],[0,420.,192.],[0,0,1.]]]),3,axis=0)
        for mode in ['pure_rotation','planar_scene','parallel_cameras','identical_camera_observations']:
            pts=world.copy();es=[];uvs=[];depths=[]
            if mode=='planar_scene':pts[:,2]=4.
            for i in range(3):
                rvec=np.array([.07*i,-.10*i,.025*i])
                center=np.array([.3*i,.10*i,0.])
                if mode=='pure_rotation':center*=0
                if mode in ['parallel_cameras','identical_camera_observations']:rvec*=0
                if mode=='identical_camera_observations':center*=0
                r=cv2.Rodrigues(rvec)[0];e=np.c_[r,-r@center]
                cam=pts@r.T+e[:,3]
                uvs.append((cam@k[i].T)[:,:2]/cam[:,2,None]);depths.append(cam[:,2]);es.append(e)
            pairs=list(itertools.combinations(range(3),2))
            m={'pair':np.repeat(np.array(pairs),len(pts),axis=0),
                'uv_i':np.vstack([uvs[i] for i,j in pairs]),'uv_j':np.vstack([uvs[j] for i,j in pairs]),
                'di':np.concatenate([depths[i] for i,j in pairs]),'dj':np.concatenate([depths[j] for i,j in pairs])}
            a,b,_,_=c.build_system({'k':k,'e':np.array(es)},m)
            info=c.rank_info(a)
            zrank=c.rank_info(a[:,2:3,:])
            initial=float(np.max(np.abs(a@np.ones(6)+b)))
            assert initial<1e-12
            if mode in ['parallel_cameras','identical_camera_observations']:
                assert zrank['rank']==0
            if mode=='identical_camera_observations':assert not info['identifiable']
            results.append({'mode':mode,'full_3d_rank':info,'depth_only_rank':zrank,
                'initial_consistency_max':initial,
                'note':'pure rotation/planarity are not blanket impossibility claims; fixed depth may constrain FoV'})
        empty={'pair':np.empty((0,2),np.int16),'uv_i':np.empty((0,2)),
            'uv_j':np.empty((0,2)),'validation':np.empty(0,bool)}
        support=matching.pair_support(empty,384,512)
        assert not support['passed']
        result={'decision':'TECHNICAL_PASS','controls':results,
            'insufficient_support_rejected':support,'scientific_improvement':False}
        stage.finish(result,'''# C0b 카메라·장면 퇴화 보조 검증

**TECHNICAL_PASS**. 실제 카메라 역투영에서 구성한 순수 회전·평면·평행 카메라·동일 관측 제어와 대응 부족 검사를 수행했다.

- 평행 카메라의 깊이축 residual은 FoV에 반응하지 않는다.
- 동일 중심·방향·관측에서는 전체 6변수가 식별되지 않는다.
- 순수 회전·평면 조건의 전체 3D와 depth-only rank는 각각 수치로 기록했다. 고정 Depth가 있는 이번 문제와 일반적인 삼각측량의 관측성을 혼동하지 않는다.
- 대응점이 없는 입력은 지원 조건 실패로 분류한다. prior만으로 얻은 계수를 보정 성공으로 보고하지 않는다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
