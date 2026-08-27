# Healthcare Data Solutions

A Streamlit web app that searches PubMed for healthcare research articles by keyword (disease, symptom, or medical domain), stores the results in MySQL, and uses AI (RAG) to surface the top 10 doctors publishing on that topic — complete with real user login/signup.

## What it does

1. **Search** — Enter a healthcare keyword (e.g. "Diabetes", "Asthma") in the app.
2. **Fetch** — If no data is saved yet for that keyword, the app queries the official PubMed API (NCBI E-utilities) and pulls up to 350 articles, fetched in safe batches of 100.
3. **Store** — Article details (PMID, title, authors, journal, publication date, abstract, DOI) are saved into a MySQL database, so repeat searches load instantly instead of re-fetching.
4. **Rank** — Authors are ranked by how many saved articles they appear on for that keyword, surfacing the top 10.
5. **Explain (RAG)** — For each top doctor, their real article titles are sent to Google's Gemini API, which generates a short, grounded summary of their apparent research focus — this is Retrieval-Augmented Generation: real retrieved data, fed to an AI to generate a reasoned explanation, not a guess.
6. **Auth** — Users sign up and log in with a hashed (bcrypt) password before accessing the app.

## Tech stack

| Layer | Tool |
|---|---|
| Data source | PubMed API (NCBI E-utilities) |
| Backend logic | Python (`requests`, `xml.etree.ElementTree`) |
| Database | MySQL |
| UI | Streamlit |
| AI / RAG | Google Gemini API (`google-genai`) |
| Auth | bcrypt (password hashing) |

## Project structure

```
├── step6_full_pipeline.py   # Core backend: PubMed fetch/parse, MySQL read/write, ranking, RAG summary, auth
├── app.py                   # Streamlit frontend: login/signup, search, Top 10 Doctors tab, Articles tab
├── .env                     # Secrets (MySQL password, API keys) — NOT committed to Git
├── .gitignore                # Excludes .env and early learning/practice scripts from version control
└── requirements.txt          # Python dependencies
```

## Setup

### 1. Install dependencies
```bash
pip install requests mysql-connector-python streamlit google-genai bcrypt python-dotenv
```

### 2. Set up MySQL
Create the database and tables in MySQL Workbench (or any MySQL client):

```sql
CREATE DATABASE healthcare_data_solutions;

USE healthcare_data_solutions;

CREATE TABLE articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pmid VARCHAR(20) UNIQUE,
    title TEXT,
    authors TEXT,
    journal VARCHAR(255),
    pub_date VARCHAR(50),
    abstract TEXT,
    doi VARCHAR(100),
    search_keyword VARCHAR(255)
);

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Create a `.env` file
In the project root, create a file named `.env` (no other extension) with:

```
MYSQL_PASSWORD=your_mysql_root_password
PUBMED_API_KEY=your_pubmed_api_key
GEMINI_API_KEY=your_gemini_api_key
```

- Get a free PubMed API key at: https://www.ncbi.nlm.nih.gov/account/settings/
- Get a free Gemini API key at: https://aistudio.google.com/apikey

`.env` is excluded from Git via `.gitignore` — never commit real secrets.

### 4. Run the app
```bash
streamlit run app.py
```
This opens the app in your browser at `http://localhost:8501`. Sign up for an account, log in, then search a keyword.

## How the RAG piece works

"RAG" = **R**etrieval + **A**ugmented + **G**eneration:
- **Retrieval**: the app pulls a doctor's real, saved article titles from the MySQL database.
- **Augmented**: those titles are inserted directly into a prompt as context.
- **Generation**: Gemini reads that real context and writes a short, grounded summary — instead of guessing from general knowledge, which it has none of for a specific doctor.

## Notes / future improvements

- Ranking is currently a simple article-count per author within one keyword's saved data. Could be extended with recency weighting, journal impact, or specialty matching.
- Old learning/practice scripts (`search.py`, step2–5 files) are kept locally for reference but excluded from version control.
- Consider adding rate-limit handling for the Gemini free tier if usage grows.
