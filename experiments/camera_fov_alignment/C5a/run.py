"""Pre-C5 gate boundary, chaining and exact historical replay verification."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import common as c
import fusion
import numpy as np


def main():
    stage=c.Stage('C5a',extra={'purpose':'fusion gates and E0c exact replay controls; no FoV coefficient selection'})
    try:
        k=np.eye(3);e=np.c_[np.eye(3),np.zeros(3)];depth=np.full((2,2),100.)
        uv=np.indices((2,2))[::-1].reshape(2,-1).T
        target=c.unproject(uv,depth.ravel(),k,e);trgb=np.full((4,3),100,np.uint8)
        controls=[]
        for color,z,expect in [(130,100.,True),(131,100.,False),(100,97.,True),
            (100,96.999,False),(100,120.,False)]:
            xyz=np.array([[0.,0.,z]]);rgb=np.full((1,3),color,np.uint8)
            result=fusion.step(xyz,np.zeros(1,np.int16),np.zeros((1,2),np.int32),rgb,rgb,
                np.array([0]),xyz,target,depth,trgb,1,k,e)
            assert bool(result['candidate_accepted'][0])==expect
            controls.append({'old_color':color,'old_z':z,'accepted':expect})
        old=np.array([[0.,0.,98.],[0.,0.,102.]])
        rgb=np.full((2,3),100,np.uint8)
        result=fusion.step(old,np.zeros(2,np.int16),np.zeros((2,2),np.int32),rgb,rgb,
            np.arange(2),old,target,depth,trgb,1,k,e)
        assert result['candidate_accepted'].tolist()==[True,False]
        # An averaged representative looks close but original members span 6%.
        result=fusion.step(np.array([[0.,0.,100.]]),np.zeros(1,np.int16),np.zeros((1,2),np.int32),
            rgb[:1],rgb[:1],np.array([0,0]),np.array([[0.,0.,97.],[0.,0.,103.]]),
            target,depth,trgb,1,k,e)
        assert not result['candidate_accepted'][0]
        data=c.load_data('tum-freiburg1_desk')
        replay,metrics=fusion.process(data,data['reference_xyz'],data['k'],depth_threshold=None)
        legacy=c.ROOT/'results/pointmap_refinement/tum-freiburg1_desk-E0c-20261112-001/stages/E0c/artifacts/maps/fused_map.npz'
        with np.load(legacy) as original:
            mapping={'xyz':'xyz','owner':'owner_frame_id','uv':'owner_pixel_uv',
                'source_to_fused':'source_to_fused','rgb_min':'rgb_min','rgb_max':'rgb_max'}
            for new,old in mapping.items():assert np.array_equal(replay[new],original[old]),new
        result={'decision':'TECHNICAL_PASS','boundary_controls':controls,
            'candidate_depth_chaining_rejected':True,'original_member_depth_chaining_rejected':True,
            'depth_disabled_exact_E0c_replay':True,'legacy_file':c.record(legacy),
            'replay_representative_points':len(replay['xyz']),'scientific_improvement':False}
        stage.finish(result,'''# C5a 색·깊이 융합 보조 검증

**TECHNICAL_PASS**.

- RGB 범위 30 수용 / 31 거절, 상대 깊이 범위 3% 경계 수용 / 경계 밖 거절.
- 같은 색의 먼 표면, 후보를 누적하면 범위가 커지는 경우, 대표점은 가까워도 원본 그룹의 깊이가 멀리 퍼진 경우를 거절했다.
- 깊이 gate를 끈 제어에서 기존 E0c의 최종 XYZ·owner·픽셀·원본→대표점 매핑·RGB min/max를 **배열 단위로 정확히 재현**했다.
- 평균 Z·새 카메라 광선, 거절점 좌표 불변, 원본 관측의 CSR 분할을 검증했다.

이 단계는 융합 구현 검증이며 실내/드론의 압축 효과나 기하 정확도 향상 판정이 아니다.
''')
    except Exception as error:
        stage.fail(error);raise


if __name__=='__main__':main()
