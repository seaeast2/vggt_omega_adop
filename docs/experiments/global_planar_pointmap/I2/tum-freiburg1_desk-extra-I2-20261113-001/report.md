# I2 FoV와 tag 전달

I0의 누출 제거 fit 대응만으로 기존 C3a solver를 실행했다. 실제 proposed와 β1 대안을 별도 저장하고 이후 K/pose를 고정했다. historical C3a 재현은 I0에 있으며 이 구간의 원본 proposed도 별도 보존한다. 태그 CSR 파일 SHA256가 전후 동일하다. LOW_SUPPORT 또는 coverage 실패는 실제 제안값 사용의 탐색적 한계로 유지한다. 평면을 보고 FoV를 조정하지 않았다.

Stage: `results/global_planar_pointmap/tum-freiburg1_desk-extra-I2-20261113-001/stages/I2`. GT_NOT_EVALUATED.
