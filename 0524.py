T= int(input())
for test_case in range(1 ,T + 1):
    N, P, B = map(int, input().split())
    A = list(map(int, input().split()))
    a=len(A)
    ad = max(A)
    ans= ans1= ans2 = 0
    for i in range(N):
        if A[i] <= ad:
            ans1 = a*B
        else:
            ans2 = ad*B + P
    ans = max(ans1, ans2)
    print(f"{test_case}{ans}")
