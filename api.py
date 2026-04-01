import requests
import json
import sys

url = "https://api.openai.com/v1/responses"


res=requests.post("http://bestapi.cz:5555/getApiKey",headers={"Authorization":f"Bearer {sys.argv[1]}"})
apikey=res.json()["apiKey"]


response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {apikey}",
        "Content-Type": "application/json"
    },
    json={
    "model": "gpt-4.1",
    "input": "Return ONLY valid JSON with this format: {\"msg\": \"...\"}. The msg should be a simple coding question."
}
)

print(response.status_code)
data = response.json()
with open("results.txt", "a", encoding="utf-8") as f:
    f.write(data["output"][0]["content"][0]["text"])
    f.write("\n")  # optional, prevents everything being on one line
print(json.loads(data["output"][0]["content"][0]["text"])["msg"])


