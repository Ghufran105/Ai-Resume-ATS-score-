# 📄 AI Resume ATS Checker

Upload a resume (PDF, DOCX or TXT) and get:

- An overall **ATS score** out of 100
- A **breakdown** by category (formatting, keywords, experience, education, structure, clarity)
- **Strengths** and **missing keywords**
- **Prioritized improvements** with example rewrites
- Optional: paste a **job description** for a targeted score

Built with [Streamlit](https://streamlit.io) and Google's Gemini Flash model.

## Run locally

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_key_here"      # Windows PowerShell: $env:GEMINI_API_KEY="your_key_here"
streamlit run app.py
```

Get a free API key at https://aistudio.google.com/app/apikey

You can also paste the key into the app's sidebar instead of setting the variable.

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (must contain `app.py` and `requirements.txt`).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, pick this repo, branch `main`, main file `app.py`.
4. Open **Advanced settings → Secrets** and add:
   ```toml
   GEMINI_API_KEY = "your_key_here"
   ```
5. Click **Deploy**.

**Never commit your API key to GitHub.**

## Changing the model

The default model is `gemini-2.5-flash`. To use another Flash model, edit the
"Gemini model" box in the sidebar, or set a `GEMINI_MODEL` environment variable / secret.

## Limitations

- Scanned (image-only) PDFs are not supported, since they contain no extractable text.
- The score is an AI estimate, not the output of a real ATS. Use it as guidance.
- Resume text is sent to the Gemini API for analysis.
