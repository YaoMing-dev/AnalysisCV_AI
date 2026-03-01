# AIreadCV — AI-Powered Resume Parser & Scorer

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white&style=flat-square" />
  <img src="https://img.shields.io/badge/Flask-REST_API-000000?logo=flask&logoColor=white&style=flat-square" />
  <img src="https://img.shields.io/badge/mBERT-Multilingual-FF6F00?style=flat-square" />
  <img src="https://img.shields.io/badge/scikit--learn-RandomForest-F7931E?logo=scikitlearn&logoColor=white&style=flat-square" />
  <img src="https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square" />
</p>

A local, API-free CV analysis system that parses PDF resumes, extracts structured information, detects industry and seniority, and scores candidates on a 0–100 scale using a hybrid rule-based + ML pipeline. Supports English and Vietnamese CVs.

---

## How It Works

```
PDF Input (EN / VI)
      │
      ▼
Text Extraction  (PyPDF + header repair + encoding cleanup)
      │
      ▼
Information Extraction  (regex pipeline)
  ├─ Contact: email, phone, GitHub, LinkedIn, portfolio
  ├─ Education: degree, school, GPA, graduation year
  ├─ Experience: job titles, dates → months calculated
  ├─ Projects: name, description, tech stack
  └─ Skills, certificates, awards, activities
      │
      ▼
mBERT Vectorization  (bert-base-multilingual-cased)
  └─ Feature vectors for ML model input
      │
      ▼
Industry Detection  (15 categories)  +  Seniority Detection  (5 levels)
      │
      ▼
Scoring Engine  (rule-based + RandomForest ensemble)
  ├─ 11 component scores (GPA, experience, projects, skills, ...)
  ├─ Industry-specific bonuses  (+0 to +35 pts)
  ├─ Red flag penalties  (-5 to -60 pts)
  └─ Job-level match adjustment  (-25 to +10 pts)
      │
      ▼
Final Score  0–100  +  grade + breakdown + red flags
```

---

## Features

**Resume Parsing**
- Extracts text from PDFs including corrupted headers and 2-column layouts
- Cleans garbled Vietnamese Unicode (e.g. `C H Ứ N G C H Ỉ` → `CHỨNG CHỈ`)
- Parses flexible date formats (`MM/YYYY`, `DD/MM/YYYY`, `"present"`, `"now"`)
- Calculates exact experience duration in months

**Scoring System**
- 11 weighted components: GPA, experience, projects, skills, awards, certificates, education, links, scholarships, activities, contact
- Industry-specific rubrics tuned to real-world hiring standards (see table below)
- 8 red flag types with quantified penalties (e.g. missing portfolio for designers: −40 pts; missing medical license for healthcare: −60 pts, absolute dealbreaker)
- Context-aware: students vs. graduates, overqualified/underqualified detection

**Industries Supported (15)**

| Domain | Key Signals |
|---|---|
| IT / Software | GitHub required (Mid+), tech stack depth, fullstack bonus |
| Data / AI | Kaggle (+8), publications (+6), ML certifications |
| Security | OSCP/CEH (+8 each), bug bounty (+10) |
| Design | Portfolio required — dealbreaker if missing |
| Marketing | Google/FB Ads certs, quantified metrics |
| Finance | CFA/CPA certs, Excel/SQL proficiency |
| Healthcare | Medical license required — absolute dealbreaker |
| Legal | Law degree required, bar exam (+15) |
| HR | SHRM/HRCI certs (−10 if missing, Mid+) |
| + 6 more | Sales, Product, QA/Testing, Operations, Content, Customer Service |

**Score Grades**

| Score | Grade |
|---|---|
| 85–100 | Excellent — hire immediately |
| 70–84 | Good — strong candidate |
| 55–69 | Average — meets requirements |
| 40–54 | Below average — needs improvement |
| 0–39 | Weak — not qualified |

**Interfaces**
- **Web UI** — drag-and-drop PDF upload, job level selector, instant score display with full breakdown
- **CLI** — score single or batch CVs from the command line, optional ML retrain

---

## Tech Stack

| Category | Technology |
|---|---|
| **Backend** | Python, Flask |
| **PDF Parsing** | PyPDF2 |
| **NLP / Embeddings** | mBERT (`bert-base-multilingual-cased`), PyTorch, Hugging Face Transformers |
| **ML Model** | scikit-learn RandomForest, XGBoost (optional) |
| **Data** | pandas, NumPy |
| **Frontend** | Vanilla HTML/CSS/JS (single page, no framework) |

> The system is fully local — no OpenAI/Gemini API calls, no usage costs, no data sent externally.

---

## Project Structure

```
AIreadCV/
├── app.py                  # Flask server — POST /read_cv, GET /
├── thebrain.py             # Core engine: CVScoringRules, CVScoringModel, CVFeatureExtractor
├── read_cv4.py             # Current extraction pipeline (v8) + mBERT vectorization
├── read_cv.py … read_cv3.py  # Archived versions (v1–v7), kept for reference
├── config.py               # Flask config, vector mode toggle
├── extract_cv_details.py   # CLI utility: test extraction on a PDF
├── compare_sheets.py       # Compare ML training data across sheets
├── index.html              # Web interface
├── requirements.txt
├── Sheet1.csv, Sheet2.csv, Sheet3.csv  # 75+ labeled CVs for ML training
└── *.pdf                   # Sample CVs for testing (EN + VI)
```

---

## API

### `POST /read_cv`

Upload a PDF and get a structured scoring response.

**Request:** `multipart/form-data` — `file` (PDF), `job_level` (`Intern` / `Entry` / `Mid` / `Senior` / `Lead`)

**Response:**
```json
{
  "success": true,
  "extracted_info": {
    "email": "...",
    "phone": "...",
    "gpa": 3.5,
    "education": "...",
    "skills": "...",
    "projects": "...",
    "links": ["https://github.com/..."]
  },
  "scoring_results": {
    "detected_industry": "IT/Software",
    "candidate_seniority": "Mid",
    "rule_score": 69.3,
    "ml_score": 59.4,
    "final_score": 61.3,
    "grade": "Average",
    "score_breakdown_details": {
      "gpa": 9.6,
      "experience": 11.0,
      "projects": 29.0,
      "skills": 14.0
    },
    "red_flags": []
  }
}
```

---

## Getting Started

### Install

```bash
git clone https://github.com/YaoMing-dev/AIreadCV-many-version-.git
cd AIreadCV-many-version-

pip install -r requirements.txt
```

### Run — Web mode

```bash
python app.py
# Open http://127.0.0.1:5000 in your browser
```

### Run — CLI mode

```bash
# Score a single CV (default: Mid level)
python thebrain.py resume.pdf

# Score for a specific level
python thebrain.py resume.pdf --job-level Senior

# Batch process a folder
python thebrain.py *.pdf --job-level Entry

# Retrain the ML model on updated training data
python thebrain.py --retrain
```

---

## Version History

| Version | File | Key Changes |
|---|---|---|
| v1 | `read_cv.py` | Basic regex extraction, English only |
| v2 | `read_cv1.py` | Added Vietnamese keyword support |
| v3 | `read_cv2.py` | 2-column PDF layout handling |
| v4 | `read_cv3.py` | mBERT vectorization, hybrid ML approach |
| **v8 (current)** | `read_cv4.py` | Robust PDF header repair, encoding cleanup, optimized regex |

---

## License

[MIT](LICENSE) © [YaoMing-dev](https://github.com/YaoMing-dev)
