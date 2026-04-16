import time
import sys
from urllib.parse import quote
import re
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium_stealth import stealth
from bs4 import BeautifulSoup

# ======================================================================
#                            설정 및 상수
# ======================================================================

# 🚨 ChromeDriver Path Setting (경로 확인 필수)
CHROMEDRIVER_PATH = "C:/Program Files/chromedriver/chromedriver.exe"
MAX_WAIT_TIME_LIST = 30  # 목록 로드 대기 시간
MAX_WAIT_TIME_DETAIL = 15  # 상세 페이지 XPath 로드 대기 시간
BASE_URL = "https://page.kakao.com"
CATEGORY_UID_NOVEL = "11"
DETAIL_URL_TEMPLATE = f"{BASE_URL}/content/{{series_id}}"


# ======================================================================
#                          Selenium 드라이버 설정
# ======================================================================

def init_driver():
    """Chrome 드라이버를 Headless 및 Stealth 설정으로 초기화합니다."""
    options = Options()

    # 안정적인 크롤링을 위한 옵션 (Headless 모드 유지)
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    options.add_argument("--log-level=3")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
        driver.set_page_load_timeout(30)

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
    except WebDriverException as e:
        # print(f"[오류] 드라이버 초기화 실패: {e}")
        sys.exit(1)


# ======================================================================
#                          Next.js JSON 추출 함수
# ======================================================================

def extract_episode_count_from_next_data(html_source: str) -> str or None:
    """
    HTML 소스에서 __NEXT_DATA__ JSON을 찾아 총 화수 정보를 추출합니다.
    """
    try:
        soup = BeautifulSoup(html_source, 'html.parser')
        next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})

        if not next_data_script:
            return None

        data = json.loads(next_data_script.string)
        page_props = data.get('props', {}).get('pageProps', {})

        if 'initialData' in page_props and page_props['initialData'] is not None:
            content_info = page_props['initialData'].get('content', {})
            total_count = content_info.get('totalEpisodeCount')

            if total_count is not None:
                formatted_count = format(total_count, ',d')
                # print(f"[성공] JSON 추출 성공 (가장 빠름): 전체 {formatted_count}화") # 제거
                return f"전체 {formatted_count}"

        return None

    except Exception:
        return None


# ======================================================================
#                          2단계 크롤링 로직 (안정성 강화)
# ======================================================================

def scrape_detail_page(driver, series_id: str) -> str:
    """
    2단계: 시리즈 상세 페이지로 이동하여 최신화수(총 화수)를 추출합니다.
    """
    url = DETAIL_URL_TEMPLATE.format(series_id=series_id)

    # 최종 화수 요소를 찾는 가장 구체적인 XPath
    xpath_episode_count = "//div[contains(@class, 'bg-bg-a-20')]//div[contains(@class, 'space-x-8pxr')]/span[starts-with(text(), '전체 ')]"
    EPISODE_COUNT_PATTERN = r'^(전체|총)\s*[\d,]+\s*(화)?$'

    try:
        driver.get(url)

        # 1. 속도 우선: HTML 소스에서 JSON 데이터 추출 시도
        episode_count_from_json = extract_episode_count_from_next_data(driver.page_source)
        if episode_count_from_json:
            return episode_count_from_json  # JSON 추출 성공 시 즉시 반환

        # 2. JSON 추출 실패 시 폴백: Selenium 대기 및 XPath 추출

        # 최종 XPath 요소 로드 대기 (안정성 강화)
        episode_count_element = WebDriverWait(driver, MAX_WAIT_TIME_DETAIL).until(
            EC.presence_of_element_located((By.XPATH, xpath_episode_count))
        )

        text_content = episode_count_element.text.strip()

        if re.match(EPISODE_COUNT_PATTERN, text_content):
            return text_content
        else:
            # 3. 최종 폴백 (BeautifulSoup)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            header_div = soup.select_one('div[class*="bg-bg-a-20"]')
            if header_div:
                episode_count_tag = header_div.select_one('span.text-el-70')
                if episode_count_tag:
                    text_content = episode_count_tag.text.strip()
                    if re.match(EPISODE_COUNT_PATTERN, text_content):
                        return text_content

            return "총 화수 정보 태그를 찾을 수 없음"

    except TimeoutException:
        return f"상세 페이지 로딩 시간 초과 ({MAX_WAIT_TIME_DETAIL}초). 핵심 요소 로드 실패."
    except Exception as e:
        return f"상세 페이지 추출 중 오류 발생: {type(e).__name__}"


# 1단계 크롤링 로직 및 보조 함수
def extract_novel_info_and_series_id(element_html: str) -> dict or None:
    """
    1단계: 목록 페이지 HTML에서 제목, 작가, 상태 및 Series ID를 추출합니다.
    """
    soup = BeautifulSoup(element_html, 'html.parser')
    link_element = soup.select_one('a[href*="/content/"]')
    if not link_element: return None

    href = link_element.get('href')
    series_id_match = re.search(r'/content/(\d+)', href)
    series_id = series_id_match.group(1) if series_id_match else None
    if not series_id: return None

    title_tag = soup.select_one('span.text-el-70 > span')
    title = title_tag.text.strip() if title_tag else "제목 없음"

    metadata_div = soup.select_one('div.text-el-50')
    author = "작가 불명"
    if metadata_div:
        texts = [t.strip() for t in metadata_div.stripped_strings if t.strip()]
        if len(texts) > 1: author = texts[1]

    status_date_div = soup.select_one('div.text-el-50:last-of-type')
    status = "상태 불명"
    update_date = "날짜 정보 불명"
    is_exclusive = ""  # [독점] 태그

    if status_date_div:
        meta_texts = [t.strip() for t in status_date_div.stripped_strings if t.strip()]
        full_text = " ".join(meta_texts)

        if "완결" in full_text:
            status = "완결"
        elif "연재중" in full_text or "업데이트" in full_text:
            status = "연재중"

        date_match = re.search(r'(\d{2}\.\d{2}\.\d{2}|\d{4}\.\d{2}\.\d{2})\s*업데이트', full_text)
        if date_match:
            date_raw = date_match.group(1).replace('.', '-')
            # '25-10-17' -> '2025-10-17' 형식으로 통일
            update_date = f"20{date_raw}" if len(date_raw) == 8 and date_raw.count('-') == 2 else date_raw

    # [독점] 뱃지 추출 시도
    badge_element = soup.select_one('div.text-el-70 span[data-t-el="badge"] span.text-tx-a-30')
    if badge_element and "독점" in badge_element.text:
        is_exclusive = "[독점]"

    return {
        "제목": title, "상태": status, "최신 업데이트": update_date,
        "작가": author, "독점여부": is_exclusive, "series_id": series_id
    }


def fetch_search_results(driver, search_url: str) -> dict or None:
    """
    Selenium으로 검색 목록 페이지를 로드하고, 첫 번째 결과의 Series ID 및 정보를 추출합니다.
    """
    try:
        driver.get(search_url)

        series_container_selector = 'div[data-t-obj*="seriesId"]'
        WebDriverWait(driver, MAX_WAIT_TIME_LIST).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, series_container_selector))
        )

        novel_elements = driver.find_elements(By.CSS_SELECTOR, series_container_selector)

        if not novel_elements:
            # print("[경고] 검색 결과 목록이 비어 있습니다.") # 제거
            return None

        first_element = novel_elements[0]
        html = first_element.get_attribute("outerHTML")
        info = extract_novel_info_and_series_id(html)

        if not info:
            # print("[오류] 첫 번째 검색 결과에서 핵심 정보 추출에 실패했습니다.") # 제거
            pass  # 에러는 반환하지 않음
        return info

    except TimeoutException:
        # print(f"[오류] 목록 로딩 시간 초과 ({MAX_WAIT_TIME_LIST}초 초과).") # 제거
        return None
    except Exception as e:
        # print(f"[오류] 목록 페이지 처리 중 오류 발생: {type(e).__name__}") # 제거
        return None


# ======================================================================
#                          메인 실행 로직
# ======================================================================

def process_novel(driver, title: str):
    """단일 소설 제목에 대한 검색 및 정보 추출을 처리합니다."""
    encoded_title = quote(title.strip())
    search_url = f"{BASE_URL}/search/result?keyword={encoded_title}&categoryUid={CATEGORY_UID_NOVEL}"

    # start_time = time.time() # 시간 측정 제거

    # 1. 목록 페이지에서 기본 정보와 Series ID 추출
    result_from_list = fetch_search_results(driver, search_url)

    if not result_from_list or not result_from_list.get("series_id"):
        print(f"❌ {title.strip()}: 검색 결과가 없거나 정보 추출에 실패했습니다.")
        return

    series_id = result_from_list.pop("series_id")
    # print(f"[2단계] 상세 페이지 접근 시도: {DETAIL_URL_TEMPLATE.format(series_id=series_id)}") # 제거

    # 2. 상세 페이지에서 최신화수 추출
    episode_count_str = scrape_detail_page(driver, series_id)

    # 3. 최종 결과 조합 및 출력
    # end_time = time.time() # 시간 측정 제거
    # elapsed_time = end_time - start_time # 시간 측정 제거

    # 3-1. 화수 숫자 추출 및 포맷팅
    match_num = re.search(r'[\d,]+', episode_count_str)
    episode_num_str = match_num.group(0).replace(',', '') if match_num else "정보 없음"
    episode_num_formatted = f"총 {episode_num_str}화" if episode_num_str != "정보 없음" else ""
    episode_num_for_output = f"{episode_num_str}화" if episode_num_str != "정보 없음" else "정보 없음"

    # 3-2. 상태 접미사 생성 ((총 XXX화/미완결) 형식)
    status = result_from_list.get("상태", "상태 불명")
    completion_status_tag = "/완결" if status == "완결" else "/미완결"
    status_suffix = f"({episode_num_formatted}{completion_status_tag})" if episode_num_formatted else ""

    # 3-3. 최종 출력 형식
    final_output_string = (
        f"제목: {result_from_list['제목']} {result_from_list.get('독점여부', '')} {status_suffix}, "
        f"상태: {status}, "
        f"최신화: {result_from_list['최신 업데이트']}, "
        f"화수: {episode_num_for_output}"
    )

    print(f"✅ {final_output_string}")


def main():
    print("---------------------------------------------------------")
    print("✨ KakaoPage 소설 최신화수 확인기 (최종 간결 버전) ✨")
    print("---------------------------------------------------------")

    driver = init_driver()

    try:
        while True:
            try:
                user_input = input("확인할 소설 제목을 입력하세요 (여러 개는 쉼표로 구분, 종료: exit): ").strip()

                if not user_input:
                    continue

                if user_input.lower() == 'exit':
                    print("프로그램을 종료합니다.")
                    break

                titles = [t.strip() for t in user_input.split(',') if t.strip()]

                for title in titles:
                    process_novel(driver, title)

                print()  # 검색 후 줄바꿈 추가

            except EOFError:
                print("\n입력 종료 (EOF). 프로그램을 종료합니다.")
                break
            except Exception as e:
                # print(f"[최종 오류] 예상치 못한 오류 발생: {type(e).__name__}: {e}") # 제거
                pass  # 오류는 조용히 무시

    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass


if __name__ == "__main__":
    main()
