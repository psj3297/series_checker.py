import datetime
import sys
import re
import time
from urllib.parse import quote
from selenium import webdriver
# 🚨 Service와 ChromeDriverManager 추가
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from difflib import SequenceMatcher
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium_stealth import stealth
from bs4 import BeautifulSoup
# 🚨 ChromeDriver Path Setting
CHROMEDRIVER_PATH = "C:/Program Files/chromedriver/chromedriver.exe"
# 🚨 Debug mode is off for minimal output
DEBUG = False


# ======================================================================
#                             Utility Functions
# ======================================================================

def clean_title(title: str) -> str:
    """Removes unnecessary prefixes from the title for comparison."""
    return re.sub(r'\s*\[(독점|단행본|PC|D)\]\s*', '', title).strip()


def title_similarity(a: str, b: str) -> float:
    """Calculates similarity between two titles."""
    a_clean = clean_title(a)
    b_clean = clean_title(b)
    similarity = SequenceMatcher(None, a_clean.lower(), b_clean.lower()).ratio()
    return similarity


def parse_date_string(date_str: str) -> str:
    """Formats date string to YYYY-MM-DD."""
    s = (
        date_str.strip()
        .strip("()")
        .replace("년", "-")
        .replace("월", "-")
        .replace("일", "")
        .replace(".", "-")
        .replace("/", "-")
        .rstrip("-")
    )
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d", "%Y%m%d%H%M%S"]:
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return date_str


# Detail Box Parsing Function
def parse_detail_box_html(html: str) -> dict:
    """Extracts information from the novel detail box HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Title (Original full title)
    title_tag = soup.select_one("div.title-wrap a[title]")
    title_text = title_tag.get("title").strip() if title_tag and title_tag.get("title") else "N/A"

    # Author
    author_tag = soup.select_one("dl.meta-author strong")
    author = author_tag.text.strip() if author_tag else "N/A"

    # Registration Date / Latest Update Date
    dates = soup.select("dl.meta-etc.meta dd")
    reg_date = dates[0].text.strip() if len(dates) > 0 else "N/A"
    latest_date = dates[1].text.strip() if len(dates) > 1 else "N/A"

    # Episode Count
    episode_tag = soup.find("dt", string=re.compile("연재수"))
    episode = episode_tag.find_next("dd").text.strip() if episode_tag and episode_tag.find_next("dd") else "N/A"

    # Status (Checking for 'New' icon)
    status = "연재중" if soup.select_one("span.xui-icon.xui-new") else "완결"

    # Create an output title that includes status/episode count for consistent formatting
    episode_info = episode.split()[0] if '화' in episode or '권' in episode else episode
    page_title_output = f"{title_text} ({episode_info}/{status})"

    return {
        "page_title": title_text,
        "page_title_output": page_title_output,  # For final print
        "author": author,
        "등록일": reg_date,
        "최신연재일": parse_date_string(latest_date),
        "연재수": episode_info,  # Simplified to just the number + unit
        "상태": status,
    }


# ======================================================================
#                             Selenium Logic
# ======================================================================

def init_driver():
    """Chrome Driver 자동 관리 및 Stealth 설정 적용"""
    options = Options()

    # 속도 및 안정성 옵션
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    # 봇 감지 회피를 위한 User-Agent 설정
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        # 🚨 핵심: ChromeDriverManager를 사용하여 드라이버 자동 설치 및 경로 지정
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Stealth 설정: 문피아 봇 차단 우회용
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver
    except Exception as e:
        raise Exception(f"드라이버 초기화 중 오류 발생: {e}")


def search_munpia_novel(driver, title: str) -> dict:
    """문피아 검색 결과 목록에서 가장 유사한 소설을 찾아 상세 정보를 추출합니다."""
    try:
        # 1. 검색 페이지 접속
        search_url = f"https://novel.munpia.com/page/hd.platinum/view/search/keyword/{quote(title)}/order/search_result"
        driver.get(search_url)
        wait = WebDriverWait(driver, 7)

        # 2. 검색 결과 리스트의 제목 요소들 모두 가져오기
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.title")))
        # 🚨 중요: 하나만 찾는 게 아니라 '모두(elements)' 찾습니다.
        title_elements = driver.find_elements(By.CSS_SELECTOR, "a.title")

        target_element = None

        # 3. 검색 결과 상위 5개를 돌며 유사도 체크
        for el in title_elements[:5]:
            found_title = el.text.strip()
            if title_similarity(title, found_title) > 0.6:
                target_element = el
                break  # 일치하는 걸 찾으면 루프 종료

        if target_element:
            # 4. 일치하는 소설 클릭하여 상세 페이지 이동
            target_element.click()

            # 5. 상세 정보 박스 로딩 대기
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dd.detail-box")))
            time.sleep(1.0)

            # 6. HTML 추출 및 파싱
            detail_box = driver.find_element(By.CSS_SELECTOR, "div.dd.detail-box")
            html = detail_box.get_attribute("outerHTML")
            info = parse_detail_box_html(html)

            return info
        else:
            # 상위 결과 중 일치하는 게 없을 때
            actual_first = title_elements[0].text.strip() if title_elements else "결과 없음"
            return {"error": f"제목 '{title}'와 일치하는 결과를 찾지 못함 (가장 가까운 결과: '{actual_first}')"}

    except TimeoutException:
        return {"error": f"'{title}' 검색 결과 로딩 시간 초과"}
    except Exception as e:
        return {"error": f"'{title}' 처리 중 오류 발생: {str(e)[:50]}"}


# ======================================================================
#                             Main Execution Block
# ======================================================================

if __name__ == "__main__":

    print("검색할 소설 제목을 입력하세요 (쉼표로 여러 제목 분리, 종료하려면 빈 입력):")
    user_input = input().strip()
    if not user_input:
        print("에러: 제목을 입력하지 않았습니다. 프로그램을 종료합니다.")
        sys.exit(1)

    titles = [title.strip() for title in user_input.split(",")]
    driver = None
    results = []

    try:
        # 🚨 Initialize driver once (Biggest speed gain)
        start_time = time.time()
        driver = init_driver()
        init_time = time.time() - start_time
        print(f"[INFO] 드라이버 초기화 완료. (소요 시간: {init_time:.2f}초)")

        for title in titles:
            results.append(search_munpia_novel(driver, title))

        # 🚨 Final Output
        print("\n[SUMMARY]")
        for result in results:
            if "error" in result:
                print(f"오류: {result.get('error')}")
            else:
                # Output format: 제목: ..., 상태: ..., 최신연재일: ..., 화수: ...
                print(
                    f"제목: {result['page_title_output']}, 상태: {result['상태']}, 최신연재일: {result['최신연재일']}, 화수: {result['연재수']}"
                )

    except WebDriverException as e:
        print(f"심각한 오류: 드라이버 초기화 실패 - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"최종 처리 중 예상치 못한 오류 발생: {e}")

    finally:
        # 🚨 Quit driver after all tasks are done
        try:
            if driver:
                driver.quit()
        except:
            pass
