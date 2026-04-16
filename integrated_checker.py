import datetime
import sys
import re
import time
import json
import concurrent.futures
from urllib.parse import quote
from difflib import SequenceMatcher
import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
from selenium_stealth import stealth
from bs4 import BeautifulSoup

# psutil 라이브러리가 설치되어 있어야 합니다.
try:
    import psutil
except ImportError:
    print("🚨 필수 라이브러리 'psutil'이 설치되지 않았습니다. 'pip install psutil'을 실행해주세요.")
    sys.exit(1)

# ======================================================================
# 🚨 1. 환경 설정 및 상수
# ======================================================================

# ⚠️ ChromeDriver 경로 설정 (사용자님의 경로에 맞게 설정했습니다.)
CHROMEDRIVER_PATH = "C:/Program Files/chromedriver/chromedriver.exe"
MAIN_TIMEOUT = 12  # 스레드 결과 대기 시간을 12초로 설정
PLATFORM_PAGE_LOAD_TIMEOUT = 10
MUNPIA_PAGE_LOAD_TIMEOUT = 15
NOVELPIA_PAGE_LOAD_TIMEOUT = 10
FAST_FAIL_TIMEOUT = 5
KAKAO_LIST_TIMEOUT = 7
KAKAO_DETAIL_TIMEOUT = 5
NOVELPIA_TIMEOUT = 10

# 카카오 상수
KAKAO_BASE_URL = "https://page.kakao.com"
KAKAO_CATEGORY_UID_NOVEL = "11"
KAKAO_DETAIL_URL_TEMPLATE = f"{KAKAO_BASE_URL}/content/{{series_id}}"


# ======================================================================
# 🚨 2. 유틸리티 및 드라이버 설정
# ======================================================================

def clean_title(title: str) -> str:
    cleaned = re.sub(r'\s*\[(독점|단행본|PC|D)\]\s*', '', title).strip()
    cleaned = re.sub(r'\s*\([^)]*\)\s*', '', cleaned).strip()
    cleaned = re.sub(r'\s*\(총\s*[\d,]+\s*화.*?\)', '', cleaned).strip()
    return cleaned


def title_similarity(a: str, b: str) -> float:
    a_clean = clean_title(a)
    b_clean = clean_title(b)
    similarity = SequenceMatcher(None, a_clean.lower(), b_clean.lower()).ratio()
    return similarity


def parse_date_string(date_str: str) -> str:
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
    if len(s.split('-')[0]) == 2:
        current_year_prefix = str(datetime.datetime.now().year)[:2]
        s = current_year_prefix + s

    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d", "%Y%m%d%H%M%S", "%y-%m-%d"]:
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def parse_episode_string(episode_str: str) -> str:
    match = re.search(r'([\d,]+)\s*(화|권|편|회|회차)', episode_str)
    return match.group(0) if match else "N/A"


def init_driver_for_thread(chromedriver_path: str, timeout: int = PLATFORM_PAGE_LOAD_TIMEOUT):
    options = Options()

    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--log-level=3")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.page_load_strategy = 'eager'

    try:
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)

        driver.set_page_load_timeout(timeout)

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
        raise WebDriverException(f"Driver initialization failed in thread: {e}")


# ======================================================================
# 🚨 3. 플랫폼별 검색 함수
# ======================================================================

# --- 네이버 시리즈 (search_series_novel) ---
def search_series_novel(driver, title: str) -> dict:
    platform = "시리즈"
    search_url = f"https://series.naver.com/search/search.series?t=novel&q={quote(title)}"

    try:
        driver.get(search_url)

        WebDriverWait(driver, 3).until(
            lambda driver: driver.execute_script('return document.readyState') == 'complete'
        )
        time.sleep(0.5)

        wait_result = WebDriverWait(driver, FAST_FAIL_TIMEOUT)

        try:
            wait_result.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.cont h3 a, div.d_no_w")))
        except TimeoutException:
            return {"platform": platform, "error": f"검색 결과 로딩 시간 초과 ({FAST_FAIL_TIMEOUT}초 내 결과 없음)"}

        items = driver.find_elements(By.CSS_SELECTOR, "ul.lst_thum_list > li") or driver.find_elements(By.CSS_SELECTOR,
                                                                                                       "div.cont")

        if not items and driver.find_elements(By.CSS_SELECTOR, "div.d_no_w"):
            return {"platform": platform, "error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음 (검색 결과 요소 없음)"}

        for item in items[:5]:
            try:
                # 1. 제목 추출
                title_element = item.find_element(By.CSS_SELECTOR, "h3 a")
                raw_title = title_element.text.strip()
                api_title = clean_title(raw_title)

                if title_similarity(title, api_title) < 0.6: continue

                info_p = item.find_element(By.CSS_SELECTOR, "p.info")
                info_text = info_p.text

                # 🚨 작가 정보 추출
                author = "N/A (작가 정보 추출 어려움)"
                try:
                    # 1. 가장 정확한 셀렉터 시도: span.author
                    author_element = item.find_element(By.CSS_SELECTOR, "p.info span.author")
                    author = author_element.text.strip()
                except NoSuchElementException:
                    # 2. 텍스트 파싱을 통한 작가명 추출 (보험)
                    if author_match := re.search(r'저자:\s*([^/]+)', info_text):
                        author = author_match.group(1).strip()
                    else:
                        # 3. '|' 기준으로 분리하여 작가로 추정되는 요소 추출
                        parts = [p.strip() for p in info_text.split('|') if p.strip() and not re.search(r'[\d,]+', p)]
                        if len(parts) >= 2 and not re.search(r'평점', parts[1]):
                            author = parts[1].strip()
                except Exception:
                    pass

                # 🚨 최신 업데이트 날짜 추출
                date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})\.', info_text)
                latest_date = parse_date_string(date_match.group(1)) if date_match else "N/A"

                # 🚨 화수 및 상태 추출
                episode_status_match = re.search(r'(총\s*[\d,]+\s*화)(/미완결|/완결)', info_text)
                latest_episode = parse_episode_string(episode_status_match.group(1)) if episode_status_match else "N/A"
                status = "완결" if episode_status_match and "/완결" in episode_status_match.group(2) else "연재중"

                return {
                    "platform": platform,
                    "title_found": api_title,  # 찾은 소설 제목 반환
                    "author": author,
                    "최신 업데이트": latest_date,
                    "상태": status,
                    "화수": latest_episode,
                }
            except Exception:
                continue

        return {"platform": platform, "error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음 (유사도 낮음)"}

    except TimeoutException:
        return {"platform": platform,
                "error": f"🚨 {platform} 페이지 로드 시간 초과 ({driver.execute_script('return arguments[0].pageLoadTimeout', driver)}초 내 실패)로 강제 종료"}
    except Exception as e:
        return {"platform": platform, "error": f"검색 페이지 처리 중 예기치 않은 오류 발생: {type(e).__name__}"}


# --- 문피아 (search_munpia_novel) ---

def parse_detail_box_html(html: str, api_title: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    author_tag = soup.select_one("dl.meta-author strong")
    author = author_tag.text.strip() if author_tag else "N/A"

    dates = soup.select("dl.meta-etc.meta dd")
    latest_date = dates[1].text.strip() if len(dates) > 1 else "N/A"

    episode = "N/A"
    try:
        episode_dt_tag = soup.find("dt", string=re.compile("연재수"))
        if episode_dt_tag:
            dd_tag = episode_dt_tag.find_next_sibling("dd")
            if dd_tag:
                episode = dd_tag.text.strip()
    except Exception:
        pass

    episode_info = parse_episode_string(episode)
    status = "연재중" if soup.select_one("span.xui-icon.xui-new") else "완결"

    return {
        "platform": "문피아",
        "title_found": api_title,
        "author": author,
        "최신 업데이트": parse_date_string(latest_date),
        "화수": episode_info,
        "상태": status,
    }


def search_munpia_novel(driver, title: str) -> dict:
    platform = "문피아"

    try:
        search_url = f"https://novel.munpia.com/page/hd.platinum/view/search/keyword/{quote(title)}/order/search_result"
        driver.get(search_url)

        try:
            wait_result = WebDriverWait(driver, FAST_FAIL_TIMEOUT)
            # 검색 결과 컨테이너 대기
            wait_result.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.list-body, .no-result-text")))
        except TimeoutException:
            pass

        if driver.find_elements(By.CSS_SELECTOR, ".no-result-text"):
            return {"platform": platform, "error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음 (검색 결과 없음)"}

        first_link = driver.find_element(By.CSS_SELECTOR, "a.title")
        page_title = first_link.text.strip()

        detail_page_url = first_link.get_attribute("href")

        if title_similarity(title, page_title) > 0.6:
            driver.get(detail_page_url)
            time.sleep(1.5)  # 페이지 이동 후 로딩 지연 안정화

            wait = WebDriverWait(driver, 5)
            # 상세 정보 박스가 로드될 때까지 대기
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dd.detail-box, div[class*='novel-info']")))

            detail_box = driver.find_element(By.CSS_SELECTOR, "div.dd.detail-box, div[class*='novel-info']")
            html = detail_box.get_attribute("outerHTML")
            info = parse_detail_box_html(html, page_title)

            return info
        else:
            return {"platform": platform, "error": f"제목 '{title}'와 검색 결과 '{page_title}'가 일치하지 않음 (유사도 낮음)"}

    except TimeoutException:
        raise

    except NoSuchElementException as e:
        return {"platform": platform,
                "error": f"'{title}' 처리 중 오류 발생 (내부 오류: NoSuchElementException - 검색 결과/상세 정보 요소를 찾지 못함)"}
    except Exception as e:
        return {"platform": platform, "error": f"'{title}' 처리 중 오류 발생 (내부 오류: {type(e).__name__})"}


# --- 노벨피아 (search_novelpia_novel) ---

def parse_detail_html_novelpia(html: str, initial_info: dict) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    final_info = {
        "platform": "노벨피아",
        "title_found": initial_info["title_found"],
        "author": soup.select_one(".writer-name, .novel-info-author a, .novel-info-author span"),
        "최신 업데이트": "N/A",
        "화수": initial_info["화수"],
        "상태": initial_info["상태"],
    }
    for k in ["author"]:
        if final_info[k] and hasattr(final_info[k], 'text'):
            final_info[k] = final_info[k].text.strip()
        else:
            final_info[k] = initial_info["author"]

    if soup.select_one(".end-info, .tag-novel_complete"):
        final_info["상태"] = "완결"

    latest_episode_tag = soup.select_one(
        "#episode_table tr.ep_style5:not([data-episode-no='']):first-child, .chapter-list > li:first-child")

    if latest_episode_tag:
        date_tag = latest_episode_tag.select_one(".ep_style2 b, .update-time")
        if date_tag:
            if match := re.search(r'(\d{2}\.\d{2}\.\d{2})', date_tag.text.strip()):
                final_info["최신 업데이트"] = parse_date_string(match.group(1).replace('.', '-'))

        if final_info["최신 업데이트"] == "N/A" and ("분 전" in latest_episode_tag.text or "시간 전" in latest_episode_tag.text):
            final_info["최신 업데이트"] = datetime.datetime.now().strftime("%Y-%m-%d (오늘)")

    return final_info


# --- 노벨피아 (search_novelpia_novel) ---
def search_novelpia_novel(driver, title: str) -> dict:
    platform = "노벨피아"
    # 'title_found' 필드를 초기화에 추가합니다.
    initial_info = {"author": "N/A", "화수": "N/A", "상태": "연재중", "title_found": "N/A"}
    target_novel_url = None

    try:
        encoded_title = quote(title)
        # 검색 URL은 그대로 유지합니다.
        search_url = f"https://novelpia.com/search/all//1/{encoded_title}?page=1&rows=30&novel_type=&sort_col=last_viewdate&list_display=list"
        driver.get(search_url)

        # 팝업/모달 제거 시도
        modal_wrapper_selectors = ".modal-backdrop, .pop-wrap, #novel-popup-modal, .hottime-modal, .dimd, [role='dialog'], .popup-wrap, [class*='modal-']"
        driver.execute_script(f"document.querySelectorAll(\"{modal_wrapper_selectors}\").forEach(el => el.remove());")

        # MAIN_TIMEOUT 대신 FAST_FAIL_TIMEOUT을 사용합니다.
        wait = WebDriverWait(driver, FAST_FAIL_TIMEOUT)

        # 검색 결과 컨테이너 대기 (h6 태그를 포함하도록 보강)
        wait.until(EC.presence_of_element_located(
            ((By.CSS_SELECTOR, ".search-result-items, .rand-item h6, .novel-list-wrapper"))))

        # 결과 목록 요소 탐색
        results = driver.find_elements(By.CSS_SELECTOR, ".rand-item, .search-result-item, .novel-list-item")

        if not results:
            return {"platform": platform, "error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음 (검색 결과 없음)"}

        # 가장 유사한 소설 찾기 로직 (유사도 0.6 이상)
        best_match_ratio = 0.6
        best_match_result = None

        for result in results:
            try:
                # 🚨 제목 추출 시도 (h6 셀렉터 추가)
                title_element = result.find_element(By.CSS_SELECTOR, ".novel-info-title, .title, .item-txt h6")
                page_title = title_element.text.strip()
                ratio = title_similarity(title, page_title)

                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    best_match_result = result

            except NoSuchElementException:
                continue
            except Exception:
                continue

        # 결과가 없으면 첫 번째 항목 사용 (유사도 낮음 경고는 출력하지 않음)
        if best_match_result is None:
            best_match_result = results[0]

        # 기본 정보 추출 (검색 목록에서)
        target_novel_url = best_match_result.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
        page_title = best_match_result.find_element(By.CSS_SELECTOR,
                                                    ".novel-info-title, .title, .item-txt h6").text.strip()
        initial_info["title_found"] = page_title

        # 작가 추출 (p.writer 셀렉터 추가)
        if best_match_result.find_elements(By.CSS_SELECTOR, ".writer, .writer_name, .item-txt p.writer"):
            initial_info["author"] = \
            best_match_result.find_elements(By.CSS_SELECTOR, ".writer, .writer_name, .item-txt p.writer")[
                0].text.strip()

        # 화수 추출 (item-txt-info 내부의 텍스트에서 추출)
        info_text = best_match_result.find_element(By.CSS_SELECTOR, ".item-txt-info, .novel-info-meta").text
        if match := re.search(r'([\d,]+)(회차|화)', info_text):
            initial_info["화수"] = match.group(0)

            # 완결 상태 확인
        try:
            best_match_result.find_element(By.CSS_SELECTOR, ".b_comp, .s_comp")
            initial_info["상태"] = "완결"
        except NoSuchElementException:
            pass

        # 상세 페이지로 이동하여 추가 정보 추출
        driver.get(target_novel_url)
        time.sleep(1.5)  # 페이지 이동 후 로딩 지연 안정화

        # 에피소드 테이블 로드 대기 및 정렬 시도 (기존 로직 유지)
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#episode_table")))
        except TimeoutException:
            pass

        try:
            # 최신 정보를 얻기 위해 오름차순 정렬 시도 (JS 호출)
            driver.execute_script("episode_sort('up');")
            time.sleep(0.5)
            first_episode_date_selector = "#episode_table tr.ep_style5:not([data-episode-no='']):first-child .ep_style2 b"
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, first_episode_date_selector)))
        except Exception:
            pass

        # 최종 정보 파싱 (기존 parse_detail_html_novelpia 재사용)
        final_info = parse_detail_html_novelpia(driver.page_source, initial_info)

        return {
            "platform": platform,
            "title_found": final_info.get('title_found'),
            "author": final_info.get('author'),
            "최신 업데이트": final_info.get('최신 업데이트'),
            "상태": final_info.get('상태'),
            "화수": final_info.get('화수'),
        }

    except TimeoutException:
        raise

    except NoSuchElementException as e:
        return {"platform": platform,
                "error": f"'{title}' 처리 중 오류 발생 (내부 오류: NoSuchElementException - 검색 결과/상세 정보 요소를 찾지 못함)"}
    except Exception as e:
        return {"platform": platform, "error": f"'{title}' 처리 중 오류 발생: {type(e).__name__}"}


# --- 카카오페이지 (search_kakao_novel) ---

def extract_episode_count_from_next_data(html_source: str) -> str or None:
    # ... (기존 로직 유지)
    try:
        soup = BeautifulSoup(html_source, 'html.parser')
        next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})
        if not next_data_script: return None
        data = json.loads(next_data_script.string)
        content_info = data.get('props', {}).get('pageProps', {}).get('initialData', {}).get('content', {})
        total_count = content_info.get('totalEpisodeCount')
        return f"전체 {format(total_count, ',d')}화" if total_count is not None else None
    except Exception:
        return None


def scrape_detail_page_kakao(driver, series_id: str) -> tuple[str, str]:
    # ... (기존 로직 유지)
    url = KAKAO_DETAIL_URL_TEMPLATE.format(series_id=series_id)
    xpath_episode_count = "//div[contains(@class, 'bg-bg-a-20')]//div[contains(@class, 'space-x-8pxr')]/span[starts-with(text(), '전체 ')]"
    EPISODE_COUNT_PATTERN = r'^(전체|총)\s*[\d,]+\s*(화|편)?$'
    TITLE_SELECTOR = 'h1[class*="text-el-80"]'

    found_title = "N/A"

    try:
        driver.get(url)

        # 제목 추출 시도 (5초 대기)
        try:
            title_element = WebDriverWait(driver, KAKAO_DETAIL_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, TITLE_SELECTOR))
            )
            found_title = title_element.text.strip()
        except TimeoutException:
            pass

        episode_count_from_json = extract_episode_count_from_next_data(driver.page_source)
        if episode_count_from_json: return episode_count_from_json, found_title

        episode_count_element = WebDriverWait(driver, KAKAO_DETAIL_TIMEOUT).until(
            EC.presence_of_element_located((By.XPATH, xpath_episode_count))
        )
        text_content = episode_count_element.text.strip()
        if re.match(EPISODE_COUNT_PATTERN, text_content): return text_content, found_title

        return "총 화수 정보 태그를 찾을 수 없음", found_title

    except TimeoutException:
        raise

    except Exception as e:
        return f"상세 페이지 추출 중 오류 발생: {type(e).__name__}", found_title


def extract_novel_info_and_series_id_kakao(element_html: str) -> dict or None:
    soup = BeautifulSoup(element_html, 'html.parser')
    link_element = soup.select_one('a[href*="/content/"]')
    if not link_element: return None

    # 시리즈 ID 추출
    series_id_match = re.search(r'/content/(\d+)', link_element.get('href'))
    series_id = series_id_match.group(1) if series_id_match else None
    if not series_id: return None

    title = "제목 없음"
    # 🚨 최종 수정: 제공된 HTML 구조에 맞춰 제목을 포함하는 <span> 태그를 명확히 타겟팅합니다.
    # ('span[class*="text-el-70"] span' 또는 대체 셀렉터)
    title_container = soup.select_one('span[class*="text-el-70"] span')
    if title_container:
        # 제목을 추출하고 공백을 정리합니다.
        title = re.sub(r'\s+', ' ', title_container.text.strip()).strip()

    # 작가 정보 추출
    metadata_div = soup.select_one('div.text-el-50')
    author = "작가 불명"
    if metadata_div:
        # div.text-el-50 내의 텍스트 스트링을 순회하여 작가 정보(세 번째 텍스트 요소로 추정)를 찾습니다.
        texts = [t.strip() for t in metadata_div.stripped_strings if t.strip()]
        # 예: ['웹소설', '판타지', '원태랑'] 중 '원태랑' 추출
        if len(texts) > 1 and len(texts) >= 3:
            author = texts[2]
        # 작가만 있을 경우 (구조에 따라 다름)
        elif len(texts) > 1:
            author = texts[1]

    # 상태 및 업데이트 날짜 추출
    status_date_div = soup.select_one('div.text-el-50:last-of-type')
    status = "상태 불명"
    update_date = "날짜 정보 불명"

    if status_date_div:
        # 해당 div 내의 모든 텍스트를 하나로 합칩니다.
        full_text = " ".join([t.strip() for t in status_date_div.stripped_strings if t.strip()])

        # 상태 추출
        status = "완결" if "완결" in full_text else ("연재중" if "업데이트" in full_text else "상태 불명")

        # 날짜 추출 (XX.XX.XX 또는 XXXX.XX.XX 형태)
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{2}|\d{4}\.\d{2}\.\d{2})\s*업데이트', full_text)
        if date_match:
            date_raw = date_match.group(1).replace('.', '-')
            update_date = parse_date_string(date_raw)  # YYYY-MM-DD 형식으로 변환

    return {
        "title_found": title,
        "상태": status, "최신 업데이트": update_date,
        "작가": author, "series_id": series_id
    }


def fetch_search_results_kakao(driver, search_url: str) -> dict or None:
    # ... (기존 로직 유지)
    try:
        driver.get(search_url)
        series_container_selector = 'div[data-t-obj*="seriesId"]'
        WebDriverWait(driver, KAKAO_LIST_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, series_container_selector))
        )
        novel_elements = driver.find_elements(By.CSS_SELECTOR, series_container_selector)
        if not novel_elements: return None

        html = novel_elements[0].get_attribute("outerHTML")
        return extract_novel_info_and_series_id_kakao(html)
    except TimeoutException:
        return None
    except Exception:
        return None


def search_kakao_novel(driver, title: str) -> dict:
    platform = "카카오페이지"
    encoded_title = quote(title.strip())
    search_url = f"{KAKAO_BASE_URL}/search/result?keyword={encoded_title}&categoryUid={KAKAO_CATEGORY_UID_NOVEL}"

    try:
        result_from_list = fetch_search_results_kakao(driver, search_url)

        if not result_from_list or not result_from_list.get("series_id"):
            return {"platform": platform, "error": f"검색 결과가 없거나 정보 추출에 실패했습니다."}

        series_id = result_from_list.pop("series_id")
        title_found_from_list = result_from_list.get("title_found", "N/A")

        episode_count_str, title_found_from_detail = scrape_detail_page_kakao(driver, series_id)

        # 🚨 수정: 목록 제목을 우선하여 '제목 없음' 오류 방지
        final_title = title_found_from_list
        if title_found_from_detail and title_found_from_detail not in ("N/A", "제목 없음"):
            final_title = title_found_from_detail

        match_num = re.search(r'[\d,]+', episode_count_str)
        episode_num_str = match_num.group(0).replace(',', '') if match_num else "정보 없음"
        episode_num_for_output = f"{format(int(episode_num_str), ',d')}화" if episode_num_str != "정보 없음" else "정보 없음"

        status = result_from_list.get("상태", "상태 불명")

        return {
            "platform": platform,
            "title_found": clean_title(final_title),
            "author": result_from_list.get('작가', 'N/A'),
            "최신 업데이트": parse_date_string(result_from_list['최신 업데이트']),
            "상태": status,
            "화수": episode_num_for_output
        }

    except TimeoutException:
        raise

    except Exception as e:
        return {"platform": platform, "error": f"'{title}' 처리 중 오류 발생 (내부 오류: {type(e).__name__})"}


# ======================================================================
# 🚨 4. 통합 검색 오케스트레이터 (병렬 처리)
# ======================================================================

def search_platform_parallel(title: str, platform_name: str, search_func) -> dict:
    """각 스레드에서 개별 드라이버를 생성하고 검색을 수행하는 래퍼 함수"""
    local_driver = None
    driver_pid = None

    # 플랫폼별 페이지 로드 타임아웃 설정
    timeout_map = {
        "시리즈": PLATFORM_PAGE_LOAD_TIMEOUT,
        "문피아": MUNPIA_PAGE_LOAD_TIMEOUT,
        "노벨피아": NOVELPIA_PAGE_LOAD_TIMEOUT,
        "카카오페이지": PLATFORM_PAGE_LOAD_TIMEOUT,
    }
    platform_timeout = timeout_map.get(platform_name, PLATFORM_PAGE_LOAD_TIMEOUT)

    try:
        local_driver = init_driver_for_thread(CHROMEDRIVER_PATH, platform_timeout)
        driver_pid = local_driver.service.process.pid

        result = search_func(local_driver, title)

        if 'platform' not in result:
            result['platform'] = platform_name

        return result

    except Exception as e:
        error_type = type(e).__name__
        if error_type == "TimeoutException":
            return {"platform": platform_name,
                    "error": f"🚨 {platform_name} 페이지 로드 시간 초과 ({platform_timeout}초 내 실패)로 강제 종료"}

        error_detail = str(e).splitlines()[0]
        return {"platform": platform_name, "error": f"병렬 실행 오류: {error_type} - {error_detail}"}

    finally:
        # 드라이버 정리 로직
        if local_driver:
            try:
                local_driver.quit()
            except:
                if driver_pid:
                    try:
                        proc = psutil.Process(driver_pid)
                        proc.terminate()
                        time.sleep(0.1)
                        if proc.is_running():
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass


def search_all_platforms_parallel(titles: list) -> dict:
    """주어진 제목 리스트에 대해 모든 플랫폼을 병렬 검색하고 결과를 통합합니다."""
    platform_functions = {
        "시리즈": search_series_novel,
        "문피아": search_munpia_novel,
        "노벨피아": search_novelpia_novel,
        "카카오페이지": search_kakao_novel,
    }
    all_results = {title: [] for title in titles}

    max_wait = MAIN_TIMEOUT

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(platform_functions)) as executor:
        for title in titles:
            print(f"\n--- [작업 시작] '{title}' 통합 검색 중 (병렬 실행 시작) ---")

            futures = []
            for platform_name, search_func in platform_functions.items():
                print(f"  -> [{platform_name}] 검색 요청 중...")
                future = executor.submit(search_platform_parallel, title, platform_name, search_func)
                futures.append((platform_name, future))

            time.sleep(1.0)

            for platform_name, future in futures:
                try:
                    result = future.result(timeout=max_wait)
                    all_results[title].append(result)
                except TimeoutError:
                    error_msg = f"병렬 실행 오류: {platform_name}에서 {max_wait}초 초과 (Timeout)"
                    all_results[title].append({"platform": platform_name, "error": error_msg})
                    future.cancel()

                except Exception as e:
                    error_msg = f"병렬 실행 오류: {type(e).__name__} ({str(e).splitlines()[0]})"
                    all_results[title].append({"platform": platform_name, "error": error_msg})

    return all_results


# ======================================================================
# 🚨 5. 최종 메인 실행 블록
# ======================================================================

if __name__ == "__main__":
    start_time = time.time()

    print(f"\n✨ 통합 웹소설 정보 검색기 (시리즈/문피아/노벨피아/카카오페이지) ✨")
    print(f"----------------------------------------------------------")

    try:
        user_input = input("검색할 소설 제목을 입력하세요 (쉼표로 여러 제목 분리, 종료하려면 빈 입력): ").strip()

        titles = [t.strip() for t in user_input.split(',') if t.strip()]
        if not titles:
            print("프로그램을 종료합니다.")
            sys.exit(0)

        results = search_all_platforms_parallel(titles)

        print("\n\n[통합 SUMMARY]")
        for title, platform_results in results.items():
            print(f"\n[검색 제목: {title}]")
            for info in platform_results:
                platform_name = info.get('platform', 'N/A')
                title_found = info.get('title_found', title)

                if "error" in info:
                    error_msg = info['error']
                    if "페이지 로드 시간 초과" in error_msg:
                        print(f"  ❌ [{platform_name}] 오류: {error_msg}")
                    elif ("소설을 찾을 수 없음" in error_msg or "검색 결과 없음" in error_msg or "정보 추출에 실패" in error_msg):
                        print(f"  ➖ [{platform_name}] 소설 없음: {error_msg}")
                    else:
                        print(f"  ❌ [{platform_name}] 오류: {error_msg}")
                else:
                    # 제목이 일치하더라도 항상 '제목:' 필드를 출력합니다. (이전 요청 반영)
                    print(
                        f"  ✅ [{platform_name}] | 제목: {title_found} | 작가: {info.get('author')} | 최신 업데이트: {info.get('최신 업데이트')} | 상태: {info.get('상태')} | 화수: {info.get('화수')}")


    except Exception as main_e:
        print(f"\n[FATAL ERROR] 프로그램 실행 중 치명적인 오류 발생: {type(main_e).__name__}: {main_e}", file=sys.stderr)
    finally:
        print(f"\n프로그램 종료. 총 소요 시간: {time.time() - start_time:.2f}초")