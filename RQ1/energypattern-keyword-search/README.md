Scripts for scraping github repositories
# Energy-Pattern Keyword Search
To replicate the results of RQ1, ...
## Prerequisites

- **Python 3.10+**
- **Docker** (for MongoDB)
- **GitHub Personal Access Token** ([create one here](https://github.com/settings/tokens))

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
GITHUB_TOKEN=<your-github-personal-access-token>
MONGO_ROOT_USERNAME=<your-mongo-username>
MONGO_ROOT_PASSWORD=<your-mongo-password>
MONGO_PORT=27017
SERVER_PASSWORD=<your-server-password>
```

### 3. Start MongoDB

```bash
docker compose up -d
```

This launches a MongoDB container on the port specified in `.env`. Data is persisted to `./data/mongodb`.

---

## Repository Selection

Use `extract_repos_from_git.py` to search GitHub for Python-dominant repositories that meet configurable thresholds (stars, contributors, recent activity) and optionally detect web frameworks via SBOM.

### Run

```bash
python -m processing_pipeline.select_repos.extract_repos_from_git \
  --min-python 70 \
  --min-stars 100 \
  --min-contributors 5 \
  --days 90 \
  --min-commits 20 \
  --max-results 200 \
  --detect-webapps \
  --require-web-frameworks \
  --out-csv repos.csv
```

> [!NOTE]
> A `GITHUB_TOKEN` environment variable is required. The script handles rate-limiting automatically.

### Key Options

| Flag | Default | Description |
|---|---|---|
| `--min-python` | `70.0` | Minimum Python language percentage |
| `--min-stars` | `100` | Minimum star count |
| `--min-contributors` | `5` | Minimum number of contributors |
| `--days` | `90` | Lookback window for activity |
| `--min-commits` | `20` | Minimum commits within the lookback window |
| `--max-results` | `200` | Max candidate repos from GitHub search |
| `--detect-webapps` | off | Detect web frameworks via GitHub SBOM |
| `--require-web-frameworks` | off | Only keep repos with a detected web framework |
| `--exclude` | – | Path to a text file of `owner/repo` names to skip |
| `--exclude-csv` | – | Path (or glob) to a CSV from a previous run to skip |
| `--shuffle-candidates` | off | Randomize candidate order for variety |
| `--pushed-range` | – | Non-overlapping pushed window, e.g. `2025-07-01..2025-07-31` |
| `--out-csv` | `repos.csv` | Output CSV path |

Results are written incrementally to the CSV file.

---

## PR Keyword Matching

Searches for energy keywords in **pull request** metadata (titles, bodies, comments, related issues and their comments) stored in MongoDB.

### Prerequisites

PR data must be **pre-fetched** into MongoDB before running this step. Use the provided fetch scripts:

```bash
# Fetch PRs for all repos listed in cfg/selected_repos.py
python -m processing_pipeline.keyword_matching.fetch_github_prs

# Fetch issues and releases
python -m processing_pipeline.keyword_matching.fetch_github_data
```

These scripts pull data from the GitHub API and store it in the local MongoDB instance.

### Run

```bash
python -m processing_pipeline.keyword_matching.extract_from_pr
```

This iterates over every repository in `cfg/selected_repos.py` and extracts keyword matches from:

- PR corpus (combined title + body)
- Individual PRs
- PR comments
- PR-related issues
- PR-related issue comments

Match results are saved as data files under `data/keywords_2/`.

---

## Comment & Documentation Keyword Matching

Searches for energy keywords in **source code comments**, **documentation files**, and **wiki pages** of locally cloned repositories.

### Prerequisites — Clone the Repositories

Each repository listed in `cfg/selected_repos.py` must be cloned locally into the `.tmp/source/` directory, following the path structure `<author>/<name>/<version>`.

For every repo entry in `cfg/selected_repos.py`, clone it at the specified version tag:

```bash
# Example for a repo: author=readthedocs, name=readthedocs.org, version=15.4.1

git clone --branch 15.4.1 --depth 1 \
  https://github.com/readthedocs/readthedocs.org.git \
  .tmp/source/readthedocs/readthedocs.org/15.4.1
```

Repeat for every repository in the `selected_repos` list. The general pattern is:

```bash
git clone --branch <version> --depth 1 \
  https://github.com/<author>/<name>.git \
  .tmp/source/<author>/<name>/<version>
```

If a repository has a wiki (the `wiki` field is set in `selected_repos`), also clone it into `.tmp/docs/`.

### Run

```bash
python -m processing_pipeline.keyword_matching.extract_from_source_code
```

This extracts keyword matches from:

- **Code comments** — parsed using tree-sitter AST for Python, C, C++, C#, JavaScript, and TypeScript
- **Documentation files** — markdown, reStructuredText, and other doc files within the repo
- **Wiki pages** — if configured for the repository

Match results are saved as data files under `data/keywords_2/`.

---

## Configuring Keywords

Keyword patterns are defined in `cfg/patterns.py` in the `patterns_raw` dictionary. Each key is a **category name** and its value is a **list of keyword strings**:

```python
patterns_raw = {
    "datatransfer": [
        "us cache", "introduc cache", "batch request", "gzip", ...
    ],
    "UI": [
        "lazy load image", "compress images", "disable animation", ...
    ],
    "code_optimization": [
        "avoid recompute", "memoize", "loop unrolling", "break early", ...
    ],
}
```

To modify the search:

- **Add keywords** — append strings to an existing category list.
- **Add a category** — add a new key-value pair to `patterns_raw`.
- **Remove keywords** — delete entries from a category list.

Keywords support regex notation (e.g. `r"socket\.io"`, `r"every\ \*\ minutes"`). The patterns are automatically sorted by word count and length via `transform_keywords()` before being used by the extractors — no manual sorting is needed.

---




## Project Structure

```
energypattern-keyword-search/
├── cfg/
│   ├── patterns.py              # Keyword patterns to search for
│   └── selected_repos.py        # List of target repositories
├── constants/
│   └── abs_paths.py             # Absolute path definitions (.tmp, .cache, data, etc.)
├── models/
│   └── Repo.py                  # Repo dataclass (author, name, version, wiki)
├── processing_pipeline/
│   ├── keyword_matching/
│   │   ├── extract_from_pr.py           # PR keyword matching (requires MongoDB)
│   │   ├── extract_from_source_code.py  # Comment/doc keyword matching (requires local clones)
│   │   ├── fetch_github_prs.py          # Pre-fetch PRs into MongoDB
│   │   ├── fetch_github_data.py         # Pre-fetch issues/releases into MongoDB
│   │   ├── services/                    # KeywordExtractor, MongoDB client, etc.
│   │   ├── model/                       # MatchSource enum
│   │   └── utils/                       # File output utilities
│   └── select_repos/
│       ├── extract_repos_from_git.py    # GitHub repo search & filtering
│       └── repo_filter.py              # Filtering logic (Python %, stars, SBOM, etc.)
├── data/                        # Output data
├── .tmp/                        # Locally cloned repos (source/) and wikis (docs/)
├── docker-compose.yml           # MongoDB container
├── .env.example                 # Environment variable template
└── requirements.txt             # Python dependencies
```