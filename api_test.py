from googleapiclient.discovery import build

API_KEY = 'AIzaSyAOXmHeBryehY8Vp0nomddRvADmUEy7Qgo'  # 여기 복사한 키
CX = '545017ae57dd743c5'  # CSE ID

service = build("customsearch", "v1", developerKey=API_KEY)
res = service.cse().list(q="테스트", cx=CX, num=1).execute()
print(res)