"""AI Resume ATS Checker - Streamlit + Google Gemini Flash."""

import json
import os
import re
from io import BytesIO
from typing import List, Optional

import streamlit as st
from docx import Document
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_CHARS = 30000  # safety limit on resume text sent to the model
MIN_CHARS = 150  # below this the file is probably scanned / empty


# ---------- Output structure we ask Gemini to follow ----------
class Section(BaseModel):
    name: str = Field(description="Category name, e.g. 'Keywords & Skills'")
    score: int = Field(description="Score from 0 to 100 for this category")
    feedback: str = Field(description="One or two sentences explaining the score")


class Improvement(BaseModel):
    priority: str = Field(description="One of: High, Medium, Low")
    issue: str = Field(description="What is wrong or missing")
    fix: str = Field(description="Concrete action to fix it")
    example: Optional[str] = Field(default=None, description="Short rewritten example, if useful")


class ATSReport(BaseModel):
    overall_score: int = Field(description="Overall ATS score from 0 to 100")
    summary: str = Field(description="Two to three sentence overall verdict")
    sections: List[Section]
    strengths: List[str]
    missing_keywords: List[str]
    improvements: List[Improvement]


PROMPT = """You are a strict, experienced ATS (Applicant Tracking System) evaluator and resume coach.

Evaluate the resume below. {jd_instruction}

Score these six categories from 0-100 and give feedback for each:
1. Formatting & Parsability (simple layout, standard headings, no tables/graphics that break parsers)
2. Keywords & Skills (relevant, specific, {kw_target})
3. Work Experience & Impact (action verbs, measurable results)
4. Education & Certifications
5. Structure & Completeness (contact info, summary, logical sections)
6. Clarity & Grammar (concise, error-free, consistent tense)

Rules:
- overall_score must reflect the category scores honestly. Do not inflate. Average resumes score 50-70.
- Give 5 to 8 improvements, ordered by priority, each specific to THIS resume (quote or refer to its content).
- missing_keywords: up to 12 important keywords/skills that are absent.
- strengths: 3 to 5 short items.
- Only use information present in the resume. Never invent experience.

{jd_block}RESUME TEXT:
\"\"\"
{resume}
\"\"\"
"""


# ---------- File reading ----------
def extract_text(uploaded_file) -> str:
    """Return plain text from a PDF, DOCX or TXT upload."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".pdf"):
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password protected.")
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if name.endswith(".docx"):
        doc = Document(BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)

    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")

    raise ValueError("Unsupported file type. Please upload PDF, DOCX or TXT.")


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------- Gemini call ----------
def get_api_key(sidebar_key: str) -> str:
    if sidebar_key.strip():
        return sidebar_key.strip()
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "")


def parse_report(raw_text: str) -> dict:
    """Parse model output into a dict, tolerating markdown fences."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.M).strip()
    data = json.loads(cleaned)
    report = ATSReport.model_validate(data)
    out = report.model_dump()
    out["overall_score"] = max(0, min(100, out["overall_score"]))
    for s in out["sections"]:
        s["score"] = max(0, min(100, s["score"]))
    return out


def analyze_resume(client, model: str, resume: str, job_description: str = "") -> dict:
    jd = job_description.strip()
    prompt = PROMPT.format(
        jd_instruction=(
            "Evaluate it against the job description provided."
            if jd
            else "No job description was given, so evaluate for general ATS-friendliness."
        ),
        kw_target="matched to the job description" if jd else "industry-standard for the candidate's field",
        jd_block=(f'JOB DESCRIPTION:\n"""\n{jd[:8000]}\n"""\n\n' if jd else ""),
        resume=resume[:MAX_CHARS],
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=ATSReport,
        ),
    )
    if not response.text:
        raise ValueError("The model returned an empty response. Try again.")
    return parse_report(response.text)


# ---------- UI ----------
def score_color(score: int) -> str:
    return "green" if score >= 75 else "orange" if score >= 50 else "red"


def render_report(report: dict):
    score = report["overall_score"]
    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric("ATS Score", f"{score}/100")
    with c2:
        st.markdown(f"**:{score_color(score)}[{'Strong' if score >= 75 else 'Needs work' if score >= 50 else 'Weak'}]**")
        st.write(report["summary"])
    st.progress(score / 100)

    st.subheader("Score breakdown")
    for s in report["sections"]:
        st.markdown(f"**{s['name']}** — :{score_color(s['score'])}[{s['score']}/100]")
        st.progress(s["score"] / 100)
        st.caption(s["feedback"])

    left, right = st.columns(2)
    with left:
        st.subheader("Strengths")
        for item in report["strengths"]:
            st.markdown(f"- ✅ {item}")
    with right:
        st.subheader("Missing keywords")
        if report["missing_keywords"]:
            st.markdown(" ".join(f"`{k}`" for k in report["missing_keywords"]))
        else:
            st.write("No major keywords missing.")

    st.subheader("Improvements")
    icons = {"high": "🔴", "medium": "🟠", "low": "🟢"}
    for imp in report["improvements"]:
        icon = icons.get(imp["priority"].strip().lower(), "⚪")
        with st.expander(f"{icon} {imp['priority']}: {imp['issue']}"):
            st.write(f"**Fix:** {imp['fix']}")
            if imp.get("example"):
                st.code(imp["example"], language=None)

    st.download_button(
        "Download report (JSON)",
        data=json.dumps(report, indent=2),
        file_name="ats_report.json",
        mime="application/json",
    )


def main():
    st.set_page_config(page_title="AI Resume ATS Checker", page_icon="📄", layout="wide")
    st.title("📄 AI Resume ATS Checker")
    st.write("Upload your resume to get an ATS score and specific improvements.")

    with st.sidebar:
        st.header("Settings")
        sidebar_key = st.text_input("Gemini API key", type="password", help="Optional if set in secrets.")
        model = st.text_input("Gemini model", value=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
        st.caption("Get a free key at aistudio.google.com/app/apikey")
        st.caption("Your resume is sent to Google's Gemini API for analysis.")

    uploaded = st.file_uploader("Resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"])
    jd = st.text_area("Job description (optional, for a targeted score)", height=150)

    if st.button("Analyze resume", type="primary", disabled=uploaded is None):
        api_key = get_api_key(sidebar_key)
        if not api_key:
            st.error("Add your Gemini API key in the sidebar or in Streamlit secrets.")
            return
        try:
            with st.spinner("Reading resume..."):
                text = clean_text(extract_text(uploaded))
        except Exception as e:
            st.error(f"Could not read the file: {e}")
            return
        if len(text) < MIN_CHARS:
            st.error(
                "Very little text was found. The file may be a scanned image or empty. "
                "Upload a text-based PDF or a DOCX."
            )
            return
        try:
            with st.spinner("Analyzing with Gemini..."):
                client = genai.Client(api_key=api_key)
                st.session_state["report"] = analyze_resume(client, model.strip() or DEFAULT_MODEL, text, jd)
        except json.JSONDecodeError:
            st.error("The model returned malformed output. Please click Analyze again.")
            return
        except Exception as e:
            msg = str(e)
            if "API key" in msg or "API_KEY" in msg or "401" in msg or "403" in msg:
                st.error("API key problem. Check that your Gemini key is valid.")
            elif "404" in msg or "not found" in msg.lower():
                st.error(f"Model '{model}' was not found. Change the model name in the sidebar.")
            elif "429" in msg or "quota" in msg.lower():
                st.error("Rate limit or quota reached. Wait a minute and try again.")
            else:
                st.error(f"Analysis failed: {msg}")
            return

    if "report" in st.session_state:
        render_report(st.session_state["report"])


if __name__ == "__main__":
    main()
