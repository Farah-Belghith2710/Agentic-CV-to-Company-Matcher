# CV Matcher

Upload your CV, choose some job postings, and see which ones you fit. Every requirement is marked
with a highlighter: green if your CV shows it, yellow if only partly, pink if it is missing. Then the
app rewrites your CV bullets for the jobs you pick, without inventing anything.

![CV Matcher](docs/screenshot-ranking.png)

## Run it

You need:

- **Python 3.10 or newer** ([python.org](https://www.python.org/downloads/))
- **Node.js**, only if there is no `frontend/dist` folder (for example after cloning from GitHub)

Then:

- **Windows:** double-click `start.bat`
- **Mac or Linux:** run `./start.sh`

Your browser opens http://localhost:8000. The first start takes a few minutes because it installs
everything; after that it starts in seconds. Keep the black window open while you use the app.

## Use it

1. **Your CV:** upload your CV as a PDF, or paste its text.
2. **Where to look:** choose where the jobs come from.
   - **Jobs you saved from LinkedIn:** drag the *Send to CV Matcher* button to your bookmarks bar,
     then click it on any LinkedIn job you like.
   - **Example postings:** 40 made-up jobs to try the app.
   - Or company career pages, remote job boards, or postings you paste.
3. Press **Find and rank jobs**.
4. Tick up to 3 jobs and press **Tailor my CV**. At the end, download the report.

## Smarter results (optional)

The app works offline with rules. For smarter matching and real rewrites, copy
`backend/.env.example` to `backend/.env`, add a free API key (Gemini or Groq) as shown in that
file, and start the app again.

## Built with

Python, FastAPI and LangGraph for the agent; React and TypeScript for the web app.

How it works, tests, settings and troubleshooting: [the full guide](docs/GUIDE.md).
