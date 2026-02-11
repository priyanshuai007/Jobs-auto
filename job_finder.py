import os
import requests
import csv
import hashlib
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

EMAIL = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print("EMAIL present:", bool(os.getenv("EMAIL_ADDRESS")))
print("EMAIL_PASSWORD present:", bool(os.getenv("EMAIL_PASSWORD")))

if not EMAIL or not EMAIL_PASSWORD:
    raise Exception("EMAIL_ADDRESS or EMAIL_PASSWORD secret is missing.")

KEYWORDS_FILE = "keywords.txt"
TODAY_FILE = "jobs_today.csv"
HISTORY_FILE = "jobs_history.json"

PREFERRED_REGIONS = ["India", "Dubai", "UAE", "Qatar", "Singapore"]

def load_keywords():
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        return [k.strip() for k in f.readlines() if k.strip()]

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(list(history), f)

def hash_job(title, company, url):
    return hashlib.md5(f"{title}{company}{url}".encode()).hexdigest()

def google_search(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": 10
    }
    r = requests.get(url, params=params)
    data = r.json()
    results = []
    for item in data.get("items", []):
        results.append({
            "title": item["title"],
            "company": item.get("displayLink", ""),
            "location": "",
            "type": "",
            "url": item["link"],
            "source": "Google Hidden Jobs"
        })
    return results

def adzuna_search(keyword, country):
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": keyword,
        "results_per_page": 20
    }

    try:
        r = requests.get(url, params=params, timeout=20)

        if r.status_code != 200:
            print(f"Adzuna error for {country} ({r.status_code})")
            return []

        try:
            data = r.json()
        except Exception:
            print(f"Adzuna returned non-JSON for {country}")
            return []

        results = []

        for j in data.get("results", []):
            results.append({
                "title": j.get("title", ""),
                "company": j.get("company", {}).get("display_name", ""),
                "location": j.get("location", {}).get("display_name", ""),
                "type": j.get("contract_type", ""),
                "url": j.get("redirect_url", ""),
                "source": "Adzuna"
            })

        return results

    except Exception as e:
        print(f"Adzuna request failed for {country}: {e}")
        return []

def remotive_search(keyword):
    url = "https://remotive.com/api/remote-jobs"
    r = requests.get(url)
    data = r.json()
    results = []
    for j in data.get("jobs", []):
        if keyword.lower() in j["title"].lower():
            results.append({
                "title": j["title"],
                "company": j["company_name"],
                "location": j["candidate_required_location"],
                "type": j["job_type"],
                "url": j["url"],
                "source": "Remotive"
            })
    return results

def detect_region(location):
    if not location:
        return "Unknown"
    for r in PREFERRED_REGIONS:
        if r.lower() in location.lower():
            return r
    if "europe" in location.lower():
        return "Europe"
    return "Other"

def send_email(new_jobs, total_jobs):
    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = EMAIL
    msg["Subject"] = f"Daily Job Digest – {datetime.utcnow().strftime('%Y-%m-%d')}"

    body = f"""
Total jobs found: {total_jobs}
New jobs today: {len(new_jobs)}

"""

    for j in new_jobs[:20]:
        body += f"{j['title']} | {j['company']} | {j['location']} | {j['url']}\n"

    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(EMAIL, EMAIL_PASSWORD)

    server.send_message(msg)
    server.quit()

def main():
    keywords = load_keywords()
    history = load_history()
    all_jobs = []
    new_jobs = []

    adzuna_countries = ["in", "sg", "ae", "qa", "gb", "fr", "de", "nl"]

    for kw in keywords:
        all_jobs.extend(remotive_search(kw))

        for c in adzuna_countries:
            all_jobs.extend(adzuna_search(kw, c))

        hidden_queries = [
            f'{kw} job',
            f'{kw} careers',
            f'{kw} site:careers',
            f'{kw} site:jobs',
            f'{kw} recruiter',
            f'{kw} consulting'
        ]

        for q in hidden_queries:
            all_jobs.extend(google_search(q))

    seen = set()
    final_jobs = []

    for j in all_jobs:
        h = hash_job(j["title"], j["company"], j["url"])
        if h in seen:
            continue
        seen.add(h)

        j["region_group"] = detect_region(j["location"])
        j["new"] = "No"

        if h not in history:
            j["new"] = "Yes"
            new_jobs.append(j)

        final_jobs.append(j)

    with open(TODAY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["New","Title","Company","Location","RegionGroup","Type","Source","URL"])
        for j in final_jobs:
            writer.writerow([
                j["new"],
                j["title"],
                j["company"],
                j["location"],
                j["region_group"],
                j["type"],
                j["source"],
                j["url"]
            ])

    for j in final_jobs:
        history.add(hash_job(j["title"], j["company"], j["url"]))

    save_history(history)

    send_email(new_jobs, len(final_jobs))

if __name__ == "__main__":
    main()
