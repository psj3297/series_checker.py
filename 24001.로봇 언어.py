T = int(input())
for test_case in range(1, T + 1):
    S = input()
    dp = [set() for _ in range(len(S)+1)] #dp는 항상 공간이 더잇어야함
    dp[0].add(0) # 초기화

    for i in range(len(dp)-1): #아까 더했으니 1빼고
        for j in dp[i]: #
            if S[i] == 'L':
                dp[i+1].add(j-1)
            elif S[i] == 'R':
                dp[i+1].add(j+1)
            elif S[i] == '?':
                dp[i+1].add(j-1)
                dp[i+1].add(j+1)
    count = 0
    for positions in dp:
        for distance in positions:
            if count < abs(distance):
                count = abs(distance)
    print(f'{count}')
