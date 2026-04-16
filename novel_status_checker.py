import datetime
import requests
import sys
import re
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from difflib import SequenceMatcher

CHROMEDRIVER_PATH = "C:/Program Files/chromedriver/chromedriver.exe"
API_KEY = 'AIzaSyAOXmHeBryehY8Vp0nomddRvADmUEy7Qgo'
CX = '545017ae57dd743c5'
DEBUG = True

# 제목 정제 (접미사 제거)
def clean_title(title: str) -> str:
    return re.sub(r'\s*\[(독점|단행본|PC)\]\s*', '', title).strip()

# 제목 유사도 계산
def title_similarity(a: str, b: str) -> float:
    a_clean = clean_title(a)
    b_clean = clean_title(b)
    similarity = SequenceMatcher(None, a_clean.lower(), b_clean.lower()).ratio()
    if DEBUG: print(f"[DEBUG] 제목 유사도: '{a_clean}' vs '{b_clean}' = {similarity:.2f}")
    return similarity

# 날짜 파싱
def parse_date_string(date_str: str) -> str:
    s = date_str.strip().strip('()').replace('년', '-').replace('월', '-').replace('일', '').replace('.', '-').replace('/', '-').rstrip('-')
    for fmt in ['%Y%m%d', '%Y-%m-%d', '%Y%m%d%H%M%S']:
        try:
            return datetime.datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except:
            continue
    return date_str

# 화수 파싱 (화수 또는 권수)
def parse_episode_string(episode_str: str) -> str:
    match = re.search(r'(\d+화|\d+권)', episode_str)
    return match.group(1) if match else "N/A"

# Google Custom Search API로 네이버 시리즈 검색
def search_naver_series(title: str) -> tuple:
    search_url = f"https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={CX}&q=\"{title}\" site:series.naver.com"
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        data = response.json()

        if DEBUG:
            print("[DEBUG] Google API 응답:", data.get('searchInformation', {}).get('totalResults', '0'))

        items = data.get('items', [])
        if not items:
            if DEBUG: print("[DEBUG] 검색 결과 없음")
            return None, None

        for item in items[:5]:
            url = item.get('link', '')
            api_title = item.get('title', '').strip()
            snippet = item.get('snippet', '')

            product_no = None
            if 'detail.series?productNo=' in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                product_no = query_params.get('productNo', [None])[0]

            if not product_no:
                match = re.search(r'productNo=(\d+)', snippet or api_title or url)
                if match:
                    product_no = match.group(1)

            if product_no and title_similarity(title, api_title) > 0.6:
                if DEBUG: print(f"[DEBUG] productNo 추출: {product_no}, API 제목: {api_title}, URL: {url}")
                return product_no, api_title

        if DEBUG: print("[DEBUG] 적합한 productNo 없음")
        return None, None
    except requests.RequestException as e:
        if DEBUG: print("[DEBUG] Google API 호출 실패:", e)
        return None, None

# 최신화 날짜 & 상태 & 화수 가져오기
def get_naver_series_latest_by_title(title: str) -> dict:
    product_no, api_title = search_naver_series(title)
    if not product_no:
        return {"error": f"제목 '{title}'에 해당하는 소설을 찾을 수 없음"}

    detail_url = f"https://series.naver.com/novel/detail.series?productNo={product_no}"

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
    try:
        driver.get(detail_url)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.title_contains(clean_title(title).strip()))

        page_title = ""
        try:
            page_title = driver.title.strip()
            if DEBUG: print(f"[DEBUG] driver.title 제목 추출: {page_title}")
        except Exception as e:
            if DEBUG: print("[DEBUG] driver.title 제목 추출 실패:", e)
            try:
                page_title = driver.find_element(By.CSS_SELECTOR, "meta[property='og:title']").get_attribute("content").strip()
                if DEBUG: print(f"[DEBUG] meta 제목 추출: {page_title}")
            except Exception as e:
                if DEBUG: print("[DEBUG] meta 제목 추출 실패:", e)

        if page_title and title_similarity(title, page_title) < 0.6:
            if DEBUG: print(f"[DEBUG] 페이지 제목 불일치: 입력='{title}', 페이지='{page_title}'")
            return {"error": f"제목 '{title}'와 페이지 제목 '{page_title}'이 일치하지 않음"}
        elif not page_title:
            if DEBUG: print(f"[DEBUG] 페이지 제목 없음, API 제목 사용: {api_title}")
            page_title = api_title

        wait.until(EC.presence_of_element_located((By.ID, "volumeList")))
        try:
            btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div[class*='_changeTicketSortOrder'] button.txt")))
            driver.execute_script("arguments[0].click();", btn)
            if DEBUG: print("[DEBUG] 최신순 버튼 JS click 완료")
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tbody#volumeList tr")))
        except Exception as e:
            if DEBUG: print("[DEBUG] 최신순 버튼 클릭 실패:", e)

        try:
            last_em = driver.find_element(By.CSS_SELECTOR, "tbody#volumeList tr:first-child em")
            latest_date = parse_date_string(last_em.text)
            if DEBUG: print("[DEBUG] 최신화 날짜:", latest_date)
        except Exception as e:
            if DEBUG: print("[DEBUG] 최신화 날짜 추출 실패:", e)
            latest_date = "N/A"

        try:
            last_episode = driver.find_element(By.CSS_SELECTOR, "tbody#volumeList tr:first-child td.subj strong").text.strip()
            latest_episode = parse_episode_string(last_episode)
            if DEBUG: print("[DEBUG] 최신화 화수:", latest_episode)
        except Exception as e:
            if DEBUG: print("[DEBUG] 최신화 화수 추출 실패:", e)
            latest_episode = "N/A"

        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "완결" in body_text or "종료" in body_text:
            status = "완결"
        elif "연재중" in body_text or "연재 중" in body_text:
            status = "연재중"
        else:
            status = "정보 부족"

        if DEBUG: print("[DEBUG] 상태:", status)
        return {
            "status": status,
            "date": latest_date,
            "episode": latest_episode,
            "product_no": product_no,
            "page_title": page_title
        }

    except Exception as e:
        if DEBUG: print("[DEBUG] Selenium 프로세스 실패:", e)
        return {"error": "상세 페이지 처리 중 오류 발생"}

    finally:
        driver.quit()

# 테스트: 명령줄 인수 또는 사용자 입력으로 제목 처리
if __name__ == "__main__":
    titles = []

    if len(sys.argv) > 1:
        titles = sys.argv[1:]
    else:
        print("검색할 소설 제목을 입력하세요 (쉼표로 여러 제목 분리, 종료하려면 빈 입력):")
        user_input = input().strip()
        if user_input:
            titles = [clean_title(title.strip()) for title in user_input.split(",")]
        else:
            print("에러: 제목을 입력하지 않았습니다. 프로그램을 종료합니다.")
            sys.exit(1)

    results = []
    for title in titles:
        print(f"\n[INFO] '{title}' 처리 중...")
        result = get_naver_series_latest_by_title(title)
        results.append(result)
        print(result)

    print("\n[SUMMARY]")
    for result in results:
        if "error" in result:
            print(f"제목: {result.get('error')}")
        else:
            print(f"제목: {result['page_title']}, 상태: {result['status']}, 최신화: {result['date']}, 화수: {result['episode']}")