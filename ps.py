def dfs(numbers, k, visited, max_value):
    # 현재 상태가 이미 방문한 상태인지 확인
    # state는 현재 숫자 배열 상태와 남은 교환 횟수로 정의
    state = (tuple(numbers), k)
    if state in visited:  # 이미 방문한 상태면 재탐색하지 않음
        return
    visited.add(state)  # 현재 상태를 방문 기록에 추가

    # 교환 횟수가 0이 되면 현재 배열 상태의 값을 계산해 최대값 갱신
    if k == 0:
        # 리스트(numbers)를 문자열로 변환 후, 정수로 바꿔서 비교
        max_value[0] = max(max_value[0], int(''.join(map(str, numbers))))
        return

    # 모든 자리 쌍(i, j)에 대해 숫자를 교환하며 탐색
    n = len(numbers)  # 숫자 배열의 길이
    for i in range(n):  # 첫 번째 선택할 숫자 위치
        for j in range(i + 1, n):  # 두 번째 선택할 숫자 위치 (i 이후)`
            # 두 숫자를 교환
            numbers[i], numbers[j] = numbers[j], numbers[i]
            # 재귀적으로 DFS 호출, 교환 횟수는 k - 1로 줄어듦
            dfs(numbers, k - 1, visited, max_value)
            # 탐색 후 교환을 원래대로 복원 (백트래킹)
            numbers[i], numbers[j] = numbers[j], numbers[i]


# 입력 처리 및 출력
T = int(input())  # 테스트 케이스 개수 입력
for test_case in range(1, T + 1):
    # 테스트 케이스에서 숫자판과 교환 횟수 입력
    data, k = input().split()  # data: 숫자판, k: 교환 횟수
    numbers = list(map(int, data))  # 숫자판을 정수 리스트로 변환
    k = int(k)  # 교환 횟수를 정수로 변환

    visited = set()  # 방문 기록을 저장할 집합
    max_value = [0]  # 최대값을 저장할 리스트 (mutable 변수로 사용)

    # DFS 탐색 시작
    dfs(numbers, k, visited, max_value)

    # 결과 출력
    print(f"#{test_case} {max_value[0]}")
