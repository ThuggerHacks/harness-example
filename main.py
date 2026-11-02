"""Mark every answer WITHOUT the marking scheme, send the results, close the run.

    pip install requests
    python mark_without_scheme.py
"""
import re
import requests

SERVER = "http://102.202.45.215:3000/api"
KEY = "msk_ecc04e1e6a96eab47729954d8ae716d8e3d5024a5bbcf4eb"
LLM_URL = "http://10.0.4.15:4000/v1"
LLM_KEY = "sk-R59HRWsZ1HM4UV5prc7Jxw"
MODEL = "qwen3.8-27b"
REPEATS = 1
QUESTION = None
ANSWER = None

H = {"Authorization": f"Bearer {KEY}"}


def ask_model(prompt):
    r = requests.post(f"{LLM_URL}/chat/completions", headers={"Authorization": f"Bearer {LLM_KEY}"},
                      json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0}, timeout=300)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


# 1. start a run
run = requests.post(f"{SERVER}/runs", headers=H, json={
    "harnessName": "harnesses/simple-no-scheme", "gitCommit": "none", "model": MODEL,
    "usedMarkingScheme": False,
}).json()
run_id = run["runId"]
print("run", run_id)

# 2. get the answers, and the question of each

params = {"runId": run_id, "pageSize": 500}
if QUESTION:
    params["questionId"] = QUESTION
if ANSWER:
    answers = [requests.get(f"{SERVER}/answers/{ANSWER}", headers=H, params={"runId": run_id}).json()["answer"]]
else:
    answers = requests.get(f"{SERVER}/answers", headers=H, params=params).json()["answers"]

questions = {}
for a in answers:
    if a["questionId"] not in questions:
        questions[a["questionId"]] = requests.get(f"{SERVER}/questions/{a['questionId']}", headers=H, params={"runId": run_id}).json()["question"]

# 3. mark each answer with the model
results = []
for repeat in range(1, REPEATS + 1):
    for a in answers:
        q = questions[a["questionId"]]
        parts = [l for l in q["lines"] if l["label"] in a["lines"]]
        prompt = (
            "You are an IGCSE Physics examiner. Mark the student's answer. You do not have the mark scheme.\n"
            "Reply only with one line per part, like 'MARK b: 2', then 'REASON: ...'.\n\n"
            + q["stem"] + "\n\n"
            + "\n\n".join(f"PART {l['label']} ({l['marks']} marks): {l['text']}\nSTUDENT: {a['lines'][l['label']]}" for l in parts)
        )
        reply = ask_model(prompt)

        lines = {}
        for l in parts:
            m = re.search(rf"MARK {re.escape(l['label'])}\s*:\s*(\d+)", reply)
            if m:
                lines[l["label"]] = {"total": min(int(m.group(1)), l["marks"])}

        result = {"answerId": a["id"], "repeat": repeat, "prompt": prompt, "rawOutput": reply}
        if len(lines) == len(parts):
            result["lines"] = lines
        else:
            result["parseFailed"] = True
        results.append(result)
        print(a["id"], repeat, lines or "unreadable")

# 4. send the results, close the run, show the score
sent = requests.post(f"{SERVER}/runs/{run_id}/results", headers=H, json={"results": results}).json()
print("stored", sent.get("stored"), sent.get("error", ""))
requests.post(f"{SERVER}/runs/{run_id}/close", headers=H)
score = requests.get(f"{SERVER}/runs/{run_id}/score", headers=H).json()
print("exact total agreement:", score["overall"]["exactTotalAgreement"])