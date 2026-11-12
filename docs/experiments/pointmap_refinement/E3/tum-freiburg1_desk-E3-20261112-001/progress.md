# E3 중간 기록

1. E2 초기 공유점·owner Ray·67,906개 후보·부모 해시를 고정했다.
2. GT를 읽지 않는 학습 프로세스로 Photo-only Ray-depth 200회를 실행했다.
3. 0/20/…/200회 체크포인트를 보존했고, 손실 기준 selected는 초기 0회였다.
4. 200회 last에서 실제 점 이동을 확인했으나 RGB 손실·PSNR·Coverage가 악화했다.
5. 실제 초기 장면의 Adam 방향 Autograd와 전체 렌더 유한차분이 일치하지 않는 경계를 기록했다.
6. 선택 이후 GT를 초기-only 단일 scale로 평가했다. RMSE/AbsRel 수치가 소폭 악화했다.
7. 초기·selected·last PLY/NPZ와 고정 RGB·CSR·비활성 좌표·Ray 제약 검증을 완료했다.
8. 실행 완료와 최적화 효과 실패를 구분해 보고·커밋·푸시한다.

[보고서](report.md) 참조.
