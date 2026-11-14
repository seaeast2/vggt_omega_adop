"""Verify O0 input hashes and the forest camera map against official C++."""
from acquire import *
import shutil
import numpy as np
from PIL import Image
from eth3d_laser_evaluate import official_binary, distort


def run(directory):
    samples=json.loads((directory/'samples.json').read_text())
    _,binary=official_binary();checks=[];count=0
    for sample in samples:
        for frame in sample['frames']:
            for key in ['image','gt_source','prepared','original_image','raw_lidar']:
                if key in frame:
                    item=frame[key];assert record(ROOT/item['path'])==item;count+=1
            with np.load(ROOT/frame['prepared']['path']) as arrays:
                assert arrays['depth_m'].shape==arrays['valid'].shape==(frame['height'],frame['width'])
                assert np.isfinite(arrays['depth_m'][arrays['valid']]).all()
                assert (arrays['depth_m'][arrays['valid']]>0).all()
                assert int(arrays['valid'].sum())==frame['valid_pixels']
            if sample['dataset']!='eth3d-forest-rig':continue
            image=np.array(Image.open(ROOT/frame['image']['path']))
            monochrome=bool(np.array_equal(image[...,0],image[...,1]) and np.array_equal(image[...,0],image[...,2]))
            assert monochrome
            cam=frame['original_camera'];xy=np.random.default_rng(0).uniform(-.5,.5,(2048,2))
            data=f"{cam['width']} {cam['height']}\n"+' '.join(map(str,cam['params']))+'\n'+'\n'.join(f'{x:.14g} {y:.14g}' for x,y in xy)+'\n'
            value=subprocess.check_output([str(binary)],input=data,text=True)
            expected=np.array([list(map(float,line.split())) for line in value.splitlines()])
            error=float(abs(expected-distort(xy,cam['params'])).max());assert error<.003
            checks.append(dict(frame=frame['name'],grayscale_channels_identical=monochrome,official_cpp_max_pixel_error=error))
    audit=dict(forest=checks,input_records_verified=count,model_inference=False,GT_accuracy_evaluated=False,
        official_camera_commit='d1bb0163229925f44ce9b52b384ab458f42712ba')
    (directory/'additional_checks.json').write_text(json.dumps(audit,indent=2))
    shutil.copy2(__file__,directory/'verify.py')
    doc=ROOT/'docs/experiments/outdoor_lidar_samples'/directory.name
    shutil.copy2(directory/'additional_checks.json',doc/'additional_checks.json')
    print(json.dumps(audit))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args();run(args.run)
