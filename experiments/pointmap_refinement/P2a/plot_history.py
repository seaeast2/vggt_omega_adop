"""Scientific log-error plot from recorded synthetic histories; CPU only."""
import argparse,json
from pathlib import Path
import cv2
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args()
rows=json.loads((a.stage/'evaluation/synthetic.json').read_text())
canvas=np.full((460,800,3),255,np.uint8)
for exponent in range(-6,0):
    y=390-int((exponent+6)/6*330)
    cv2.line(canvas,(85,y),(760,y),(220,220,220),1)
    cv2.putText(canvas,f'1e{exponent}',(10,y+5),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
colors=[(210,80,20),(20,20,220),(30,140,30)]
for idx,(r,color) in enumerate(zip(rows,colors)):
    points=np.array([[85+int(v['step']/199*675),390-int((np.log10(max(v['mean_3d_error'],1e-6))+6)/6*330)] for v in r['history']],np.int32)
    cv2.polylines(canvas,[points],False,color,2)
    cv2.putText(canvas,r['backend'],(100+idx*210,30),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
cv2.putText(canvas,'iteration (0-199); mean 3D error, synthetic units, log scale',(85,435),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
assert cv2.imwrite(str(a.stage/'artifacts/synthetic/recovery_history.png'),canvas)
