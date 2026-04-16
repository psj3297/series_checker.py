from youtube_comment_downloader import YoutubeCommentDownloader
import re

def is_spam_username(username):
    return bool(re.search(r'(상단|위에|프사|체널|클릭|들어가봐|OF|에디션|디럭스|쥰내|킹)', username, re.IGNORECASE))

def is_spam_comment(text):
    spam_keywords = [
        '감정선', '진짜 몰입', '감사합니다', '반복하게 됨', '레전드',
        '숨멎었음', '완전 장악', '자연스럽게', '빠져들', '체험하는 느낌',
        '감탄 포인트', '정신 놓쳤네', '개념이 아님', '몰입은 처음', '계속 반복',
    ]
    return any(keyword in text for keyword in spam_keywords)

def detect_spam_comments(video_url):
    # Shorts 링크를 watch?v= 형태로 바꾸기
    if 'shorts/' in video_url:
        video_url = video_url.replace("shorts/", "watch?v=")

    downloader = YoutubeCommentDownloader()
    comments = downloader.get_comments_from_url(video_url, sort_by=0)  # 인기순

    print("\n🔍 [스팸 댓글 및 계정 탐지 결과]")
    for c in comments:
        user = c['author']
        text = c['text']
        if is_spam_username(user) or is_spam_comment(text):
            print(f"🚨 계정: {user} \n🗨️ 댓글: {text}\n")

if __name__ == "__main__":
    url = input("유튜브 영상 URL 입력: ")
    detect_spam_comments(url)
