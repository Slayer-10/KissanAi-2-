import requests, json
url = 'http://127.0.0.1:8000/analyze'
files = {'text': (None, 'mere qareeb gandum ka mandi rate batao')}
resp = requests.post(url, data=files)
print('Status', resp.status_code)
print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
