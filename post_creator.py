import requests
from bs4 import BeautifulSoup
import sys
import time
import datetime

# 게시글 작성 폼 및 전송 URL 정의
GET_FORM_URL = "https://cafe345.com/bbsweb/xtbbs.php?group_name=chobo&mode=w&bbs_id="
POST_WRITE_URL = "https://cafe345.com/bbsweb/write_p.php"

# 모든 게시판 ID 목록
BBS_IDS = [
    "20250528083219",
    "20250528083243",
    "20250528083253",
    "20250622204843",
    "20250622204900",
    "20250622204914"
]

# 게시글 내용 (1부터 10까지 반복 사용)
contents_list = [str(i) for i in range(1, 11)]


def create_post_with_manual_cookies(
        cookies: dict,
        subject: str,
        content: str,
        target_bbs_id: str,
        is_anonymous: bool = False,
        youtube_url: str = None,
        attachment_path: str = None
):
    """
    cafe345.com 웹사이트에 게시글을 작성합니다.
    수동 추출한 쿠키를 사용하며, CSRF 토큰을 처리합니다.
    """
    session = requests.Session()
    session.cookies.update(cookies)

    form_url = f"{GET_FORM_URL}{target_bbs_id}"
    print(f"\n[게시판 {target_bbs_id}] 폼 요청: {form_url}")

    try:
        response_get = session.get(form_url)
        response_get.raise_for_status()
        soup = BeautifulSoup(response_get.text, 'html.parser')
        form_tag = soup.find('form', {'action': 'write_p.php'})

        if not form_tag:
            print(f"[게시판 {target_bbs_id}] 오류: 작성 폼을 찾을 수 없습니다. HTML 구조 변경 가능성.")
            return False

        csrf_token_data = {h.get('name'): h.get('value') for h in form_tag.find_all('input', type='hidden') if
                           h.get('name')}

    except requests.exceptions.RequestException as e:
        print(f"[게시판 {target_bbs_id}] 폼 요청 오류: {e}")
        return False

    payload = {"subject": subject, "content": content, **csrf_token_data}
    if is_anonymous: payload["is_anonymous"] = "1"
    if youtube_url: payload["youtube_url"] = youtube_url

    files = {}
    if attachment_path:
        try:
            files['attachment'] = (
            attachment_path.split('/')[-1].split('\\')[-1], open(attachment_path, 'rb'), 'application/octet-stream')
            print(f"파일 '{attachment_path}' 첨부.")
        except FileNotFoundError:
            print(f"오류: 첨부 파일 '{attachment_path}'를 찾을 수 없습니다.")
            return False

    print(f"[게시판 {target_bbs_id}] 게시글 POST 요청 전송 (제목: '{subject}')")
    try:
        response_post = session.post(POST_WRITE_URL, data=payload, files=files) if files else session.post(
            POST_WRITE_URL, data=payload)
        response_post.raise_for_status()

        print(f"[게시판 {target_bbs_id}] 게시글 작성 성공. (서버 응답은 HTML 페이지)")
        return True

    except requests.exceptions.RequestException as e:
        print(f"[게시판 {target_bbs_id}] 게시글 POST 요청 오류: {e}")
        return False
    finally:
        for f in files.values():
            if hasattr(f[1], 'close'): f[1].close()


if __name__ == "__main__":
    print("--- 수동 쿠키를 이용한 게시글 자동 작성 스크립트 ---")
    print("웹 브라우저에서 로그인 후 쿠키 정보를 추출하여 입력해주세요.")
    print("\n--- 쿠키 추출 방법 ---")
    print("1. 브라우저(Chrome/Edge/Firefox)에서 cafe345.com 로그인")
    print("2. 'F12' 눌러 개발자 도구 열기 -> 'Application' (또는 'Storage') 탭 선택")
    print("3. 왼쪽 메뉴 'Cookies' -> 'cafe345.com' 클릭")
    print("4. 'PHPSESSID', 'user_id' 등 필요한 쿠키의 'Name'과 'Value' 복사")
    print("   예시: `PHPSESSID:xxxxxxxxxxxxxxxxxx, user_id:xxxxxxxxxxxxxxxxxx`")

    cookies_str = input("\n쿠키를 '이름:값' 형태로 쉼표로 구분하여 입력하세요: ")
    manual_cookies = {}
    try:
        for pair in cookies_str.split(','):
            if ':' in pair:
                name, value = pair.split(':', 1)
                manual_cookies[name.strip()] = value.strip()
            else:
                print(f"경고: 유효하지 않은 쿠키 형식: '{pair}' (무시됨)")
    except Exception as e:
        print(f"오류: 쿠키 파싱 실패: {e}. 스크립트를 종료합니다.")
        sys.exit(1)

    if not manual_cookies:
        print("오류: 입력된 쿠키가 없습니다. 스크립트를 종료합니다.")
        sys.exit(1)

    print(f"\n성공적으로 쿠키 입력됨: {manual_cookies.keys()}")

    # --- 게시글 작성 순환 로직 (게시판별 시간당 10개, 총 60개/시간) ---
    post_counter = 0

    while True:
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        print(f"\n======== {current_time} - 게시글 작성 순환 시작 (총 {post_counter}개 글 작성됨) ========")

        for bbs_id in BBS_IDS:
            content_to_use = contents_list[post_counter % len(contents_list)]  # 내용 순환

            print(f"\n--- 게시판 ({bbs_id})에 게시글 작성 시도 (제목: '{content_to_use}') ---")
            create_post_with_manual_cookies(
                cookies=manual_cookies,
                subject=content_to_use,
                content=content_to_use,
                target_bbs_id=bbs_id,
                is_anonymous=True
            )
            post_counter += 1

            # 각 게시글 작성 후 60초 대기 (1시간에 총 60개 글 목표)
            print(f"다음 게시글 작성을 위해 {60}초 대기합니다. (현재 총 {post_counter}개 글 작성)")
            time.sleep(60)

        print(
            f"\n======== {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} - 모든 게시판에 한 번씩 글 작성을 완료했습니다. 다음 순환 시작. ========")