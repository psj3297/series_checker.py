import time
import csv
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

ALL_FILE = "novels_all.csv"
NEW_FILE = "novels_new_completed.csv"

def get_html_selenium(url):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # User-Agent를 일반 크롬 브라우저와 동일하게 설정
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/115.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.get(url)

    try:
        # 완결작 목록이 나올 때까지 최대 15초 대기
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".book_wrap"))
        )
    except Exception as e:
        print("리스트 로딩 실패 or 셀렉터 없음:", e)

    html = driver.page_source
    driver.quit()
    return html

def crawl_munpia_complete_page(page=1):
    url = f"https://novel.munpia.com/complete?page={page}"
    html = get_html_selenium(url)
    soup = BeautifulSoup(html, 'html.parser')

    novels = []
    items = soup.select('.book_wrap')
    if not items:
        print("목록을 찾지 못했습니다. 셀렉터 확인 필요.")
        # 디버깅용 html 일부 출력
        print(html[:500])
        return novels

    for item in items:
        title_tag = item.select_one('.tit_book a')
        if not title_tag:
            continue
        title = title_tag.text.strip()
        detail_url = "https://novel.munpia.com" + title_tag['href']
        novels.append({
            "제목": title,
            "URL": detail_url
        })
    return novels

def crawl_munpia_detail(url):
    html = get_html_selenium(url)
    soup = BeautifulSoup(html, 'html.parser')

    # 완결 여부 확인
    status_tag = soup.select_one('.book_info .status')
    if status_tag:
        status_text = status_tag.text.strip()
        completed = "완료" if "완결" in status_text else "연재"
    else:
        completed = "연재"

    # 완결 날짜 가져오기 (예: .book_info 내 날짜 관련 정보)
    end_date = ""
    date_tags = soup.select('.book_info .date_info li')
    for tag in date_tags:
        text = tag.text.strip()
        if "완결" in text:
            end_date = text.replace("완결", "").strip()
            break

    return completed, end_date

def load_existing():
    if not os.path.exists(ALL_FILE):
        return {}
    data = {}
    with open(ALL_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['플랫폼'], row['제목'])
            data[key] = row
    return data

def save_results(results, existing):
    with open(ALL_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["플랫폼", "제목", "완결여부", "완결일", "URL"])
        writer.writeheader()
        writer.writerows(results)

    new_completed = []
    for r in results:
        key = (r['플랫폼'], r['제목'])
        if r['완결여부'] == "완료" and (key not in existing or existing[key]['완결여부'] != "완료"):
            new_completed.append(r)

    if new_completed:
        with open(NEW_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["플랫폼", "제목", "완결여부", "완결일", "URL"])
            writer.writeheader()
            writer.writerows(new_completed)

    print(f"[완료] 총 {len(results)}건 저장, 신규 완결 {len(new_completed)}건 발견")

if __name__ == "__main__":
    existing_data = load_existing()
    all_results = []

    # 1페이지부터 3페이지만 예시로 수집 (원하는 만큼 늘리세요)
    for page in range(1, 4):
        novels = crawl_munpia_complete_page(page)
        if not novels:
            break
        for novel in novels:
            completed, end_date = crawl_munpia_detail(novel["URL"])
            all_results.append({
                "플랫폼": "문피아",
                "제목": novel["제목"],
                "완결여부": completed,
                "완결일": end_date,
                "URL": novel["URL"]
            })

    save_results(all_results, existing_data)
