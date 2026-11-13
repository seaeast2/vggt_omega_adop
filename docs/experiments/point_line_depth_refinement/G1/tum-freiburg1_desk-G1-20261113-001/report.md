# G1 관측 동결

영상에서 공통 모니터의 위·아래·오른쪽 테두리를 확인하고 LSD 선분을 대응시켰다. 선 지원 기준 미달이므로 후속 선 실험은 탐색적이다.

```json
{
  "decision": "LOW_SUPPORT_DIAGNOSTIC_ONLY",
  "line_support": [
    {
      "pair": [
        0,
        1
      ],
      "fit_tracks": 2,
      "validation_tracks": 1,
      "passed": false
    },
    {
      "pair": [
        0,
        2
      ],
      "fit_tracks": 1,
      "validation_tracks": 1,
      "passed": false
    },
    {
      "pair": [
        1,
        2
      ],
      "fit_tracks": 1,
      "validation_tracks": 1,
      "passed": false
    }
  ],
  "tracks": [
    {
      "structure": "screen_top",
      "validation": false,
      "observations": {
        "0": [
          34.56614303588867,
          102.88302612304688,
          99.826904296875,
          90.50818634033203
        ],
        "1": [
          226.17311096191406,
          86.17544555664062,
          338.32012939453125,
          75.1008529663086
        ],
        "2": [
          412.5211181640625,
          105.44271850585938,
          510.9810485839844,
          117.7844009399414
        ]
      },
      "reviewer": "Codex RGB visual review; not correspondence GT"
    },
    {
      "structure": "screen_bottom",
      "validation": true,
      "observations": {
        "0": [
          201.54161071777344,
          175.6870880126953,
          69.28530883789062,
          212.805419921875
        ],
        "1": [
          356.7735595703125,
          171.10003662109375,
          236.86447143554688,
          186.79457092285156
        ],
        "2": [
          510.77301025390625,
          228.38377380371094,
          390.6513671875,
          210.4483642578125
        ]
      },
      "reviewer": "Codex RGB visual review; not correspondence GT"
    },
    {
      "structure": "screen_right",
      "validation": false,
      "observations": {
        "0": [
          190.89163208007812,
          132.36598205566406,
          204.41104125976562,
          181.6439208984375
        ],
        "1": [
          355.47174072265625,
          117.84561157226562,
          359.9864501953125,
          175.9658966064453
        ]
      },
      "reviewer": "Codex RGB visual review; not correspondence GT"
    }
  ],
  "sample_counts": {
    "fit": 70,
    "validation": 80
  },
  "observations_frozen_at": "2026-11-13T12:12:21.045760+09:00",
  "point_support": {
    "pairs": [
      {
        "pair": [
          0,
          1
        ],
        "total": 30,
        "fit": 24,
        "validation": 6,
        "occupied_4x4_cells": [
          7,
          8
        ],
        "passed": false
      },
      {
        "pair": [
          0,
          2
        ],
        "total": 11,
        "fit": 8,
        "validation": 3,
        "occupied_4x4_cells": [
          5,
          5
        ],
        "passed": false
      },
      {
        "pair": [
          1,
          2
        ],
        "total": 16,
        "fit": 15,
        "validation": 1,
        "occupied_4x4_cells": [
          6,
          5
        ],
        "passed": false
      }
    ],
    "passed": false
  },
  "note": "Monitor borders only; parallel/adjacent edges correlated. No manual line endpoint refinement. Plane fit fixed before G2."
}
```

실행 경로: `results/point_line_depth_refinement/tum-freiburg1_desk-G1-20261113-001/stages/G1`

GT 정확도는 미평가이며 대응 지원 부족 결과는 탐색적이다.
