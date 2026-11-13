"""H6a extra raw E0 reference and A0-fixed zoom/plane-color visual aids; no fitting."""
from base import *
from evaluate import match_metrics,wall_metrics

def run():
 st=Stage('H6a',parents=[latest('H6')],extra={'purpose':'E0 raw numerical reference; fixed A0-only zoom; shared-plane color overlays; no pointcloud or fit changes'})
 try:
  data=load();raw=data.copy();raw['k']=c.load_data('tum-freiburg1_desk')['k'];raw['xyz']=c.points(raw,np.ones(6));zeros=np.zeros(len(data['xyz']),bool);rawgeo=match_metrics(raw,raw['xyz'],zeros);basegeo=match_metrics(data,data['xyz'],zeros);rawwall=wall_metrics(data,raw['xyz'],st.path/'artifacts/baseline/E0_raw_sections')
  f=np.load(latest('H2c')/'artifacts/masks/fixed_wall_reference.npz');ids=f['ids'];normal=f['normal'];center=f['center'];Dref=float(np.median(data['d0'][ids]));signed=(data['xyz'][ids]-center)@normal;lo,hi=np.percentile(signed,[.1,99.9]);margin=max((hi-lo)*.15,.0002*Dref);ylim=(float(lo-margin),float(hi+margin));basis=np.array([1.,0,0]);basis-=basis@normal*normal;basis/=np.linalg.norm(basis);ss=(data['xyz'][ids]-center)@basis;xlo,xhi=np.percentile(ss,[.1,99.9]);width,height=800,500
  def plot(xyz,label):
   canvas=np.full((height,width,3),250,np.uint8);dist=(xyz[ids]-center)@normal;clipped=[]
   # Axes use A0 observations only, exactly the same for every arm.
   for tick in np.linspace(ylim[0],ylim[1],5):
    py=int(440-(tick-ylim[0])/(ylim[1]-ylim[0])*380);c.cv2.line(canvas,(80,py),(780,py),(225,225,225),1);c.cv2.putText(canvas,f'{tick/Dref:+.4f}',(3,py+5),0,.4,(70,70,70),1)
   for source in range(3):
    sel=data['fid'][ids]==source;x=((xyz[ids][sel]-center)@basis-xlo)/(xhi-xlo)*680+90;y=440-(dist[sel]-ylim[0])/(ylim[1]-ylim[0])*380;good=(x>=80)&(x<790)&(y>=45)&(y<450);clipped.append({'frame':source,'points':int(sel.sum()),'outside_plot':int((~good).sum())});canvas[y[good].astype(int),x[good].astype(int)]=c.PALETTE[source]
   c.cv2.putText(canvas,label,(85,22),0,.6,(20,20,20),1);c.cv2.putText(canvas,'fixed A0 wall ROI | red=frame0 green=frame1 | signed distance / Dref',(85,480),0,.42,(30,30,30),1);return canvas,clipped
  plots=[];names=[];clips=[];im,cl=plot(data['xyz'],'C3a A0');plots.append(im);names.append('C3a_A0');clips.append({'name':'A0','sources':cl})
  for code,name in [('H3d','A1_FRAME_RAWMASK'),('H3d','A2_FRAME_REFINED'),('H4d','A3_SHARED_RAWMASK'),('H4d','A4_SHARED_REFINED'),('H5d','A5_SHARED_SOFT')]:
   parent=latest(code);path=parent/'artifacts/arms'/name/'proposed/pointmap.npz';z=np.load(path);xyz=z['xyz'];im,cl=plot(xyz,code+' '+name);plots.append(im);names.append(code+'_'+name);clips.append({'name':names[-1],'sources':cl});c.image_write(st.path/f'artifacts/figures/{names[-1]}_zoom.png',im)
   for camera in range(3):
    local=z['local_plane_id'].reshape(3,384,512)[camera];shared=z['shared_plane_id'].reshape(3,384,512)[camera];accepted=z['accepted'].reshape(3,384,512)[camera];display=data['rgb'][camera].copy();colors=np.random.default_rng(0).integers(30,255,(max(1,int(shared.max())+1),3));hit=shared>=0;display[hit]=np.rint(.35*display[hit]+.65*colors[shared[hit]]).astype(np.uint8);display[hit&~accepted]=[255,0,255];c.image_write(st.path/f'artifacts/figures/{names[-1]}_camera{camera}_shared_planes.png',display)
   c.json_write(st.path/f'evaluation/{names[-1]}_provenance.json',{'frozen_proposal':c.record(path),'changes_to_geometry':False,'plane_color_random_seed':0,'magenta':'shared candidate rejected by hard target gate','no_shared_group':'unchanged original image'})
  c.image_write(st.path/'artifacts/figures/C3a_A0_zoom.png',plots[0]);canvas=np.full((height*2,width*3,3),250,np.uint8)
  for ix,im in enumerate(plots):canvas[(ix//3)*height:(ix//3+1)*height,(ix%3)*width:(ix%3+1)*width]=im
  c.image_write(st.path/'artifacts/figures/wall_zoom_comparison.png',canvas)
  m={'decision':'VISUAL_REFERENCE_COMPLETED','E0_raw_geometry':rawgeo,'C3a_geometry':basegeo,'E0_raw_fixed_C3a_wall':rawwall,'fixed_zoom':{'x_limits':[float(xlo),float(xhi)],'signed_distance_limits':ylim,'Dref':Dref,'limits_from':'A0 only p0.1/p99.9 plus 15pct margin','clipping':clips},'pointcloud_refit_or_modification':False}
  report='# H6a E0 참고 수치·벽 확대 단면·공유 평면색\n\nH6의 전체 audit 이후, 계획의 E0 raw 참고 수치와 육안 확인용 확대 단면을 보완했다. 최적화·마스크·점군은 다시 계산하지 않았다. E0의 원래 K로 얻은 matching 지표와 C3a K의 matching 지표를 구분하며 C3a 고정 관측 ID·평면으로 E0 벽을 참고 측정했다. GT 비교가 아니다.\n\n확대 축은 보정 결과를 보지 않고 A0의 signed distance p0.1/p99.9에 15% 여백을 더해 고정했다. 모든 군에 같은 축을 사용했고 잘린 점 수를 기록했다. 빨강=frame0, 초록=frame1이며 기존 벽 ROI에 frame2 지지는 없다. 공유 평면색 overlay는 같은 shared ID를 같은 색으로, hard gate 거절은 자홍색으로 표시한다. RGB/프레임색 PLY는 원본 그대로다.\n\n![고정 범위 확대 단면](figures/wall_zoom_comparison.png)\n'
  st.finish(m,report)
  with (DOC/'summary.md').open('a') as stream:stream.write(f'\n\n[E0 참고·벽 확대 단면·공유 평면색 H6a]({st.doc.relative_to(DOC)}/report.md)\n')
  with (DOC/'index.md').open('a') as stream:stream.write(f'| H6a | 완료·시각화/참고 수치 | [{st.run_id}]({st.doc.relative_to(DOC)}/report.md) |\n')
 except Exception as e:st.fail(e);raise
if __name__=='__main__':run()
