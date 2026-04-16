from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
import time

# 크롬 드라이버 경로 설정

# chromedriver.exe의 절대 경로를 입력 (본인이 압축푼 경로)
service = Service(r"C:\Users\psj52\Downloads\chromedriver-win64\chromedriver.exe")
driver = webdriver.Chrome(service=service)

try:
    # 유튜브 영상 열기 (영상 ID 바꿔서 사용)
    driver.get('https://www.youtube.com/shorts/AnJY15QOGhk')

    time.sleep(5)  # 페이지 로딩 대기

    # 댓글 영역 스크롤 (댓글 로딩을 위해)
    driver.execute_script("window.scrollTo(0, 600);")
    time.sleep(3)

    # 더 스크롤 내리면서 댓글 추가 로딩
    for i in range(5):
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(2)

    # 댓글 요소 수집 (댓글 텍스트가 들어있는 div 클래스명 기준)
    comments = driver.find_elements(By.XPATH, '//*[@id="content-text"]')

    # 필터링 키워드 리스트
    spam_keywords = ['스팸', '광고', '클릭', '체널', '구독']

    for comment in comments:
        text = comment.text
        if any(keyword in text for keyword in spam_keywords):
            print(f'[필터됨] {text}')
            # 숨기기 시도 (JS 실행 - display:none;)
            driver.execute_script("arguments[0].style.display='none';", comment)

    print("필터링 완료")

finally:
    # 종료 시 잠시 대기 후 종료
    time.sleep(10)
    driver.quit()
