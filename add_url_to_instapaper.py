import requests

INSTAPAPER_ADD_URL = "https://www.instapaper.com/api/add"

USERNAME = "lucas.lindh6@live.se"
PASSWORD = "nenziN-xunqoj-nebmo1"

ARTICLE_URL = "https://luckepucke6.github.io/kobo-pages-test/"

payload = {
    "username": USERNAME,
    "password": PASSWORD,
    "url": ARTICLE_URL,
    "title": "Testartikel från GitHub Pages",
}

r = requests.post(INSTAPAPER_ADD_URL, data=payload, timeout=20)

print("Status:", r.status_code)
print("Response:", r.text)
