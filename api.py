import requests
import json
import sys
import argparse
import requests

url = "https://api.openai.com/v1/responses"

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--password", required=True, help="API password/token")

args = parser.parse_args()

res = requests.post(
    "http://bestapi.cz:5555/getApiKey",
    headers={"Authorization": f"Bearer {args.password}"}
)

result=res.json()

if "apiKey" not in result.keys():
    sys.exit("wrong password")

apikey = result["apiKey"]

# response = requests.post(
#     url,
#     headers={
#         "Authorization": f"Bearer {apikey}",
#         "Content-Type": "application/json"
#     },
#     json={
#     "model": "gpt-4.1",
#     "input": "Return ONLY valid JSON with this format: {\"msg\": \"...\"}. The msg should be a simple coding question."
# }
# )

# print(response.status_code)
# data = response.json()
# with open("results.txt", "a", encoding="utf-8") as f:
#     f.write(data["output"][0]["content"][0]["text"])
#     f.write("\n")  # optional, prevents everything being on one line
# print(json.loads(data["output"][0]["content"][0]["text"])["msg"])


def get_question_and_answers(topic,passwd):
    res=requests.post("http://bestapi.cz:5555/getApiKey",headers={"Authorization":f"Bearer {passwd}"})
    apikey=res.json()["apiKey"]


    response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {apikey}",
        "Content-Type": "application/json"
    },
    json={
    "model": "gpt-4.1",
    "input": "Return ONLY valid JSON with this format: {\"msg\": \"...\"}. "+f"The topic of question is {topic} also add keys 1 2 3 where 3 is the correct answer"
    }
    )

    print(response.status_code)
    data = response.json()
    return json.loads(data["output"][0]["content"][0]["text"])
    
    
    
if __name__ == "__main__":
    print(get_question_and_answers("bodybuilding"))
