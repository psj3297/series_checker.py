import datetime
import sys
import re
import time
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium_stealth import stealth
from bs4 import BeautifulSoup

# ==========================================================
# 🚨 1. 환경 설정 및 전역 변수
# ==========================================================

# ⚠️ 반드시 본인의 환경에 맞게 경로를 수정하세요.
CHROMEDRIVER_PATH = "C:/Program Files/chromedriver/chromedriver.exe"
DEBUG = False  # 스크린샷 저장 및 상세 디버그 메시지 출력 여부
MAIN_TIMEOUT = 30  # 웹 드라이버 전체 타임아웃


# ==========================================================
# 🚨 2. 유틸리티 및 파싱 함수
# ==========================================================

def parse_date_string(date_str: str) -> str:
    """날짜 문자열을 YYYY-MM-DD 형식으로 변환합니다."""
    s = date_str.strip().strip("()").replace("년", "-").replace("월", "-").replace("일", "").replace(".", "-").replace("/",
                                                                                                                    "-").rstrip(
        "-")
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d", "%Y%m%d%H%M%S"]:
        try:
            if len(s.split('-')[0]) == 2: s = '20' + s
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def parse_detail_html(html: str, initial_info: dict) -> dict:
    """BS4를 사용하여 소설 상세 HTML에서 정보를 추출하고 선 추출 정보를 병합합니다."""
    soup = BeautifulSoup(html, "html.parser")

    final_info = {
        "page_title": soup.select_one(".novel-info-title, h1.title") or "N/A",
        "author": soup.select_one(".writer-name, .novel-info-author a, .novel-info-author span") or "N/A",
        "최신연재일": "N/A",
        "화수": initial_info["화수"],
        "상태": initial_info["상태"],  # 🚨 '연재중' 또는 선 추출된 '완결' 상태를 초기값으로 사용
    }
    for k in final_info:
        if isinstance(final_info[k], object) and hasattr(final_info[k], 'text'):
            final_info[k] = final_info[k].text.strip()

    # 완결 상태 추출 (상세 페이지 정보가 최우선)
    for tag in soup.select(".meta-info li, .novel-detail-meta span, .info-box dd"):
        if "완결" in tag.text or "종료" in tag.text:
            final_info["상태"] = "완결"
            break

    # 최신 연재일 추출 로직
    first_episode_tag = soup.select_one(
        "#episode_table tr.ep_style5:not([data-episode-no='']), .chapter-list > li:nth-child(1)")
    if first_episode_tag:
        date_tag = first_episode_tag.select_one(".ep_style2 b")
        if date_tag:
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{2})', date_tag.text.strip())
            if date_match:
                final_info["최신연재일"] = parse_date_string(date_match.group(1).replace('.', '-'))

        if final_info["최신연재일"] == "N/A" and ("분 전" in first_episode_tag.text or "시간 전" in first_episode_tag.text):
            final_info["최신연재일"] = datetime.datetime.now().strftime("%Y-%m-%d (오늘)")

    # 선 추출 작가 정보 병합
    if final_info["author"] == "N/A" and initial_info["author"] != "N/A":
        final_info["author"] = initial_info["author"]

    return final_info


# ==========================================================
# 🚨 3. Selenium 드라이버 초기화
# ==========================================================

def init_driver():
    """Headless 및 Stealth 설정을 사용하여 Chrome Driver를 초기화합니다."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("window-size=2560x1440")
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument(
        "user-agent=Mozilla/50 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"드라이버 초기화 오류: {e}. 경로: {CHROMEDRIVER_PATH}를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    stealth(driver, languages=["ko-KR", "ko"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    return driver


# ==========================================================
# 🚨 4. 메인 검색 및 추출 로직
# ==========================================================

def search_novelpia_novel(driver, title: str) -> dict:
    """Novelpia를 검색하고 세부 정보를 추출합니다."""
    # 🚨 수정: 기본 상태를 '연재중'으로 설정합니다.
    initial_info = {"author": "N/A", "화수": "N/A", "상태": "연재중"}
    try:
        encoded_title = quote(title)
        search_url = f"https://novelpia.com/search/all//1/{encoded_title}?page=1&rows=30&novel_type=&start_count_book=&end_count_book=&novel_age=&start_days=&sort_col=last_viewdate&novel_genre=&block_out=0&block_stop=0&is_contest=0&is_complete=0&is_challenge=0&list_display=list"
        driver.get(search_url)
        wait = WebDriverWait(driver, MAIN_TIMEOUT)

        # 팝업 제거 및 페이지 로딩 대기
        modal_wrapper_selectors = ".modal-backdrop, .pop-wrap, #novel-popup-modal, .hottime-modal, .dimd, [role='dialog'], .popup-wrap, [class*='modal-']"
        driver.execute_script(f"document.querySelectorAll(\"{modal_wrapper_selectors}\").forEach(el => el.remove());")
        wait.until(
            EC.presence_of_element_located(((By.CSS_SELECTOR, ".rand-item, .search-result-item, .novel-info-title"))))

        # 페이지 이동 처리
        if not re.search(r'novel/(\d+)$', driver.current_url):
            results = driver.find_elements(By.CSS_SELECTOR, ".rand-item, .search-result-item")
            if not results:
                return {"error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음 (검색 결과 없음)"}

            # 검색 결과에서 정보 선 추출
            first_result = results[0]
            if first_result.find_elements(By.CSS_SELECTOR, ".writer, .writer_name"):
                initial_info["author"] = first_result.find_elements(By.CSS_SELECTOR, ".writer, .writer_name")[
                    0].text.strip()
            if match := re.search(r'(\d+)(회차|화)', first_result.text):
                initial_info["화수"] = match.group(1) + "화"

            # 완결 상태 확인 (검색 결과 페이지에서)
            try:
                first_result.find_element(By.CSS_SELECTOR, ".b_comp")
                initial_info["상태"] = "완결"
            except NoSuchElementException:
                if any("완결" in span.text for span in first_result.find_elements(By.CSS_SELECTOR, ".item-tags span")):
                    initial_info["상태"] = "완결"
                # 연재중인 경우 initial_info["상태"]는 '연재중'으로 유지됨.

            # 상세 페이지로 이동
            driver.get(first_result.find_element(By.CSS_SELECTOR, "a").get_attribute("href"))

        # 상세 페이지 동적 콘텐츠 로드 및 정렬
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#episode_table")))
        except TimeoutException:
            print("[WARN] 에피소드 목록 컨테이너가 3초 내에 로드되지 않았습니다. 스크롤/정렬 시도.")

        driver.execute_script("window.scrollTo(0, 1000);")
        try:
            WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#episode_table"))).click()
        except:
            pass

        try:
            driver.execute_script("episode_sort('up');")
            time.sleep(0.3)

            WebDriverWait(driver, 3).until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#episode_table tr.ep_style5:nth-child(1) .ep_style2 b")))
        except TimeoutException:
            print("[WARN] 최신 에피소드 날짜 엘리먼트가 3초 내에 출현하지 않았습니다. 현재 HTML로 추출 시도.")
        except Exception:
            print("[WARN] JS 함수 호출 실패. 현재 HTML로 추출 시도.")

        # 최종 정보 파싱
        final_info = parse_detail_html(driver.page_source, initial_info)

        if final_info.get("화수") == "N/A" and final_info.get("author") != "N/A":
            print("[WARN] 최종 추출 결과, 화수/날짜 정보가 N/A입니다. 웹사이트 로딩 지연 또는 파싱 오류가 발생했을 수 있습니다.")

        return final_info

    except TimeoutException:
        return {"error": f"'{title}' 페이지 로딩 시간 초과 ({MAIN_TIMEOUT}초)"}
    except Exception as e:
        return {"error": f"'{title}' 처리 중 오류 발생: {str(e)[:50]}..."}


# ==========================================================
# 🚨 5. 메인 실행 블록
# ==========================================================

if __name__ == "__main__":
    start_time = time.time()
    driver = None

    print(f"\n노벨피아 웹소설 정보 추출기 (직접 Selenium 검색 모드)")
    print(f"--------------------------------------------------")

    try:
        driver = init_driver()

        user_input = input("검색할 소설 제목을 입력하세요 (쉼표로 여러 제목 분리, 종료하려면 빈 입력): ")

        titles = [t.strip() for t in user_input.split(',') if t.strip()]
        if not titles:
            print("프로그램을 종료합니다.")
            sys.exit(0)

        results = {}
        for title in titles:
            print(f"\n[작업 시작] '{title}' 검색 중...")
            result = search_novelpia_novel(driver, title)
            results[title] = result

        print("\n[SUMMARY]")
        for title, info in results.items():
            if "error" in info:
                print(f"오류: '{title}' {info['error']}")
            else:
                print(
                    f"성공: '{title}' | 작가: {info.get('author')} | 최신 업데이트: {info.get('최신연재일')} | 상태: {info.get('상태')} | 화수: {info.get('화수')}")

    except Exception as main_e:
        print(f"\n[FATAL ERROR] 프로그램 실행 중 치명적인 오류 발생: {main_e}", file=sys.stderr)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        print(f"\n프로그램 종료. 총 소요 시간: {time.time() - start_time:.2f}초")