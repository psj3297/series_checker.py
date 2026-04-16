import datetime
import sys
import re
from urllib.parse import urlparse, parse_qs, quote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from difflib import SequenceMatcher
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# 🚨 ChromeDriver 경로 설정
CHROMEDRIVER_PATH = "C:/Users/psj52/PycharmProjects/PythonProject/chromedriver.exe"
# 🚨 DEBUG 모드 해제
DEBUG = False


# ======================================================================
#                             유틸리티 함수
# ======================================================================

def clean_title(title: str) -> str:
    """제목에서 불필요한 접미사([독점] 등)와 괄호 속 정보(화수/완결)를 제거합니다."""
    # [독점], [단행본], [PC] 제거
    cleaned = re.sub(r'\s*\[(독점|단행본|PC)\]\s*', '', title).strip()

    # 괄호 속의 내용 (화수/완결 정보 등) 제거
    cleaned = re.sub(r'\s*\([^)]*\)\s*', '', cleaned).strip()

    return cleaned


def title_similarity(a: str, b: str) -> float:
    """두 제목의 유사도를 계산합니다."""
    a_clean = clean_title(a)
    b_clean = clean_title(b)
    similarity = SequenceMatcher(None, a_clean.lower(), b_clean.lower()).ratio()
    return similarity


def parse_date_string(date_str: str) -> str:
    """날짜 문자열에서 YYYY-MM-DD 형식의 날짜를 추출합니다."""
    s = date_str.strip().strip('()').replace('년', '-').replace('월', '-').replace('일', '').replace('.', '-').replace('/',
                                                                                                                    '-').rstrip(
        '-')
    for fmt in ['%Y%m%d', '%Y-%m-%d', '%Y%m%d%H%M%S']:
        try:
            return datetime.datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            continue
    date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})\.', date_str)
    if date_match:
        return date_match.group(1).replace('.', '-')
    return date_str


def parse_episode_string(episode_str: str) -> str:
    """문자열에서 화수 또는 권수를 추출합니다."""
    match = re.search(r'(\d+화|\d+권)', episode_str)
    return match.group(1) if match else "N/A"


# ======================================================================
#                             Selenium 로직
# ======================================================================

def init_driver():
    """Chrome Driver 자동 관리 및 초기화"""
    options = Options()

    # 기존에 설정하신 옵션들 유지
    options.add_argument("--log-level=3")
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    })
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.page_load_strategy = 'eager'

    try:
        # 🚨 핵심: ChromeDriverManager().install()이 자동으로 경로를 잡아줍니다.
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise Exception(f"드라이버 자동 업데이트 중 오류 발생: {e}")

def search_naver_series_selenium(driver, title: str) -> dict:
    """네이버 시리즈 검색 페이지에서 소설 정보를 추출합니다. (드라이버 재사용)"""
    search_url = f"https://series.naver.com/search/search.series?t=novel&q={quote(title)}"

    # 드라이버 재사용: 새로운 URL로 이동
    driver.get(search_url)

    try:
        WebDriverWait(driver, 10).until(
            lambda driver: driver.execute_script('return document.readyState') == 'complete'
        )
    except Exception:
        pass

    # 🚨 안정화 지연 시간 1.0초 -> 0.5초로 단축 시도
    time.sleep(0.5)

    try:
        current_url = driver.current_url
        if current_url.startswith("data:"):
            return {"error": "드라이버가 네이버 페이지를 로드하지 못함 (초기화 문제)"}

    except Exception:
        return {"error": "페이지 로딩 중 드라이버 충돌"}

    try:
        # 🚨 1단계 (결과 없음 확인): 검색 결과 없음 컨테이너(div.d_no_w)를 2초 동안 먼저 확인
        wait_none = WebDriverWait(driver, 2)
        try:
            wait_none.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.d_no_w")))
            return {"error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음"}
        except TimeoutException:
            pass

            # 🚨 2단계 (검색 결과 확인): 검색 결과 요소(div.cont h3 a)가 5초 동안 나타나기를 확인
        wait_result = WebDriverWait(driver, 5)
        wait_result.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.cont h3 a")))

    except TimeoutException:
        return {"error": "검색 결과 요소 로딩 시간 초과"}

    except Exception:
        return {"error": "검색 페이지 처리 중 예기치 않은 오류 발생"}

    # 🚨 검색 결과 추출
    items = driver.find_elements(By.CSS_SELECTOR, "ul.lst_thum_list > li")

    if not items:
        items = driver.find_elements(By.CSS_SELECTOR, "div.cont")

    if not items:
        return {"error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음"}

    for item in items[:5]:
        try:
            # 1. 제목 및 URL 추출
            title_element = item.find_element(By.CSS_SELECTOR, "h3 a")
            api_title = title_element.text.strip()
            url = title_element.get_attribute('href')

            # 2. productNo 추출
            product_no = None
            if 'detail.series?productNo=' in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                product_no = query_params.get('productNo', [None])[0]

            # 3. 제목 유사도 확인 (0.6 이상 필터링)
            if not product_no or title_similarity(title, api_title) < 0.6:
                continue

            # 4. 정보 추출 (날짜, 화수, 완결 여부)
            info_p = item.find_element(By.CSS_SELECTOR, "p.info")
            info_text = info_p.text

            date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})\.', info_text)
            latest_date = parse_date_string(date_match.group(1)) if date_match else "N/A"

            episode_status_match = re.search(r'(총\d+화)(/미완결|/완결)', info_text)
            latest_episode = parse_episode_string(episode_status_match.group(1)) if episode_status_match else "N/A"
            status = "완결" if episode_status_match and "/완결" in episode_status_match.group(2) else "연재중"

            return {
                "status": status,
                "date": latest_date,
                "episode": latest_episode,
                "product_no": product_no,
                "page_title": api_title
            }

        except Exception:
            continue

    return {"error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음"}


# ======================================================================
#                             메인 실행 블록
# ======================================================================

if __name__ == "__main__":
    titles = []

    if len(sys.argv) > 1:
        titles = sys.argv[1:]
    else:
        print("검색할 소설 제목을 입력하세요 (쉼표로 여러 제목 분리, 종료하려면 빈 입력):")
        user_input = input().strip()
        if user_input:
            titles = [title.strip() for title in user_input.split(",")]
        else:
            print("에러: 제목을 입력하지 않았습니다. 프로그램을 종료합니다.")
            sys.exit(1)

    driver = None
    results = []

    try:
        # 🚨 드라이버를 단 한 번만 초기화합니다.
        driver = init_driver()

        for title in titles:
            result = search_naver_series_selenium(driver, title)  # 재사용된 드라이버로 검색
            results.append(result)

            # 요청하신 단일 형식으로 출력
            if result.get('error'):
                print(f"오류: {result.get('error')}")
            else:
                print(
                    f"제목: {result['page_title']}, 상태: {result['status']}, 최신화: {result['date']}, 화수: {result['episode']}")

    except WebDriverException as e:
        print(f"심각한 오류: 드라이버 초기화 실패 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"최종 처리 중 예상치 못한 오류 발생: {e}")

    finally:
        # 🚨 모든 작업이 끝난 후 드라이버를 종료합니다.
        try:
            if driver:
                driver.quit()
        except:
            pass