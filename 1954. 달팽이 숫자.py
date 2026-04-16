T = int(input())
di = [0, 1, 0, -1]  # 우 하 좌 상
dj = [1, 0, -1, 0]
# 여러개의 테스트 케이스가 주어지므로, 각각을 처리합니다.
for test_case in range(1, T + 1):
    N = int(input())
    arr = [[0]*N for _ in range(N)]
    i,j,cnt,dr = 0,0,1,0
    arr[i][j] =cnt
    cnt += 1
    while cnt <= N*N:
        ni = i + di[dr]
        nj = j + dj[dr]
        if 0<=ni<N and 0<=nj<N and arr[ni][nj]==0: # 범위 내에 있으면서 다음 좌표가 0이라면
            i, j = ni, nj
            arr[i][j]=cnt
            cnt += 1
        else: #방향 이동
            dr = (dr+1)%4
    print(f'#{test_case}')
    for lst in arr:
        print(*lst)




