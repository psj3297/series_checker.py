T = int(input())
# 여러개의 테스트 케이스가 주어지므로, 각각을 처리합니다.
for test_case in range(1, T + 1):
    N = int(input())
    A = list(map(int, input().split()))
    B = list(map(int, input().split()))
    team = ['']*(N+1)
    unselected = set(range(1,N+1))
    for i in range(N):
        if i%2==0:
            for player in A:
                if player in unselected:
                    team[player]='A'
                    unselected.remove(player)
                    break
        else:
            for player in B:
                if player in unselected:
                    team[player]='B'
                    unselected.remove(player)
                    break
    print(''.join(team[1:]))