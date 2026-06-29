import json
import csv
import re
import math
from datetime import datetime

CANDIDATES_FILE = "candidates.jsonl"
OUTPUT_FILE = "team_akims.csv"

REQUIRED_SKILLS = {
    "python": 12,
    "embeddings": 12,
    "retrieval": 12,
    "ranking": 12,
    "llm": 8,
    "vector": 10,
    "faiss": 8,
    "elasticsearch": 8,
    "opensearch": 8,
    "qdrant": 8,
    "milvus": 8,
    "pinecone": 8,
    "weaviate": 8,
    "machine learning": 8,
    "nlp": 7,
    "evaluation": 8,
    "ndcg": 8,
    "mrr": 8,
    "map": 8,
    "ab testing": 6,
    "a/b testing": 6,
    "production": 10,
}

GOOD_TITLES = [
    "ai engineer", "ml engineer", "machine learning engineer",
    "data scientist", "nlp engineer", "search engineer",
    "ranking engineer", "applied scientist", "software engineer"
]

BAD_TITLES = [
    "marketing", "accountant", "civil", "mechanical",
    "operations", "customer support", "hr manager"
]


def text_norm(text):
    return str(text or "").lower()


def collect_candidate_text(c):
    parts = []

    profile = c.get("profile", {})
    parts.extend([
        profile.get("headline", ""),
        profile.get("summary", ""),
        profile.get("current_title", ""),
        profile.get("current_industry", ""),
    ])

    for job in c.get("career_history", []):
        parts.extend([
            job.get("title", ""),
            job.get("industry", ""),
            job.get("description", ""),
        ])

    for edu in c.get("education", []):
        parts.extend([
            edu.get("degree", ""),
            edu.get("field_of_study", ""),
            edu.get("institution", ""),
        ])

    for skill in c.get("skills", []):
        parts.append(skill.get("name", ""))

    for cert in c.get("certifications", []):
        parts.extend([
            cert.get("name", ""),
            cert.get("issuer", ""),
        ])

    return text_norm(" ".join(parts))


def skill_score(c, text):
    score = 0

    for skill, weight in REQUIRED_SKILLS.items():
        if skill in text:
            score += weight

    for s in c.get("skills", []):
        name = text_norm(s.get("name", ""))
        prof = text_norm(s.get("proficiency", ""))
        duration = s.get("duration_months", 0) or 0
        endorsements = s.get("endorsements", 0) or 0

        if any(req in name for req in REQUIRED_SKILLS):
            score += 5
            if prof == "expert":
                score += 5
            elif prof == "advanced":
                score += 4
            elif prof == "intermediate":
                score += 2

            score += min(duration / 12, 5)
            score += min(endorsements / 10, 4)

    return score


def experience_score(c):
    profile = c.get("profile", {})
    yoe = profile.get("years_of_experience", 0) or 0

    if 5 <= yoe <= 9:
        return 25
    elif 4 <= yoe < 5:
        return 18
    elif 9 < yoe <= 11:
        return 15
    elif 3 <= yoe < 4:
        return 8
    else:
        return 2


def title_score(c, text):
    score = 0

    for title in GOOD_TITLES:
        if title in text:
            score += 10

    for title in BAD_TITLES:
        if title in text:
            score -= 15

    return score


def production_score(text):
    keywords = [
        "production", "deployed", "real users", "scale",
        "index", "search", "retrieval", "ranking",
        "evaluation", "a/b", "ab testing", "offline benchmark"
    ]

    return sum(5 for k in keywords if k in text)


def behavioral_score(c):
    s = c.get("redrob_signals", {})
    score = 0

    score += (s.get("profile_completeness_score", 0) or 0) * 0.08

    if s.get("open_to_work_flag"):
        score += 5

    if s.get("verified_email"):
        score += 2

    if s.get("verified_phone"):
        score += 2

    if s.get("linkedin_connected"):
        score += 2

    response_rate = s.get("recruiter_response_rate", 0) or 0
    score += response_rate * 8

    interview_rate = s.get("interview_completion_rate", 0) or 0
    score += interview_rate * 6

    github = s.get("github_activity_score", -1)
    if github and github > 0:
        score += min(github / 10, 8)

    notice = s.get("notice_period_days", 90) or 90
    if notice <= 30:
        score += 5
    elif notice <= 60:
        score += 2
    elif notice >= 120:
        score -= 4

    if s.get("willing_to_relocate"):
        score += 3

    return score


def suspicious_penalty(c, text):
    penalty = 0
    profile = c.get("profile", {})
    yoe = profile.get("years_of_experience", 0) or 0

    skills = c.get("skills", [])
    if len(skills) > 25:
        penalty += 15

    if yoe < 3 and ("senior" in text or "principal" in text):
        penalty += 10

    if "chatgpt" in text and "production" not in text:
        penalty += 8

    bad_count = sum(1 for t in BAD_TITLES if t in text)
    if bad_count >= 2:
        penalty += 15

    return penalty


def generate_reason(c):
    profile = c.get("profile", {})
    skills = [s.get("name", "") for s in c.get("skills", [])]
    top_skills = ", ".join(skills[:5]) if skills else "limited listed skills"

    yoe = profile.get("years_of_experience", "N/A")
    title = profile.get("current_title", "Candidate")
    location = profile.get("location", "N/A")

    return (
        f"{title} with {yoe} years of experience; relevant skills include {top_skills}. "
        f"Ranked based on AI/retrieval skill match, production relevance, experience fit, and Redrob activity signals."
    )


def score_candidate(c):
    text = collect_candidate_text(c)

    score = 0
    score += skill_score(c, text)
    score += experience_score(c)
    score += title_score(c, text)
    score += production_score(text)
    score += behavioral_score(c)
    score -= suspicious_penalty(c, text)

    return round(max(score, 0), 4)


def main():
    candidates = []

    with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                score = score_candidate(c)
                candidates.append((c["candidate_id"], score, generate_reason(c), c))

    candidates.sort(key=lambda x: (-x[1], x[0]))

    top_100 = candidates[:100]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])

        for rank, (candidate_id, score, reasoning, c) in enumerate(top_100, start=1):
            writer.writerow([candidate_id, rank, score, reasoning])

    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()