"""Scientific optimization history; values read from preserved checkpoints."""
import argparse,json
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);a=p.parse_args();rows=json.loads((a.stage/'evaluation/checkpoint_history.json').read_text())
canvas=np.full((440,1100,3),255,np.uint8)
for panel in range(2):
    x0=65+panel*550
    for tick in range(6):
        y=370-tick*60;cv2.line(canvas,(x0,y),(x0+460,y),(220,220,220),1)
        label=f'{tick*.04:.2f}' if panel==0 else str(tick*5)
        cv2.putText(canvas,label,(x0-50,y+5),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,0,0),1)
    cv2.putText(canvas,'checkpoint step 0-200',(x0+120,410),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
cv2.putText(canvas,'training Charbonnier (lower is better)',(65,28),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
cv2.putText(canvas,'fixed E1 mask PSNR (higher is better)',(615,28),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
points=np.array([[65+int(r['step']/200*460),370-int(r['training_charbonnier']/.2*300)] for r in rows]);cv2.polylines(canvas,[points],False,(40,40,210),2)
for i,color in enumerate([(220,80,20),(20,140,20),(20,80,220)]):
    points=np.array([[615+int(r['step']/200*460),370-int(r['frames'][i]['psnr_fixed_e1_mask']/25*300)] for r in rows]);cv2.polylines(canvas,[points],False,color,2);cv2.putText(canvas,f'frame {i}',(650+i*125,55),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
assert cv2.imwrite(str(a.stage/'artifacts/renders/training_history.png'),canvas)
