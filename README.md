# ICSME 2026 Energy Patterns Replication Package

This repository contains the replication package for my Master thesis: "Understanding Energy Patterns in Python Web Applications: Taxonomy, Impact, and Automated Identification. The project structure is organized by Research Questions (RQs), with each folder containing the necessary data, scripts, and instructions to replicate the results.

## Project Structure

```text
.
├── RQ1/                              # Project selection and keyword search
│   ├── data/                         # Raw matches and curated data
│   └── energypattern-keyword-search/ # Keyword search and project selection scripts
├── RQ2/                              # Energy experiments
│   ├── data/                         # Raw energy results
│   ├── energy_experiments/           # Measurement scripts for Mealie and Frappe
│   ├── results_analysis/             # Analysis and plotting scripts
│   └── scaphandre/                   # Custom Scaphandre version
└── RQ3/                              # Antipattern detector tool and validation
    ├── energypattern-LLM-tool/       # Source code and test inputs
    └── tool_validation/              # Validation results
```

## How to Replicate

The following sections detail the steps to replicate the results for each research question. 

### Replicating RQ1: Project Selection & Keyword Search
1. **Prerequisites & Setup**: Ensure you have Python 3.10+ and Docker installed. Install dependencies (`pip install -r requirements.txt`), configure your environment variables (GitHub token and MongoDB credentials in `.env`), and start MongoDB with `docker compose up -d`.
2. **Repository Selection**: Run `python -m processing_pipeline.select_repos.extract_repos_from_git` with the desired filtering thresholds (e.g., minimum stars, python percentage) to discover candidate repositories and output a list.
3. **PR Keyword Matching**: Pre-fetch PR metadata into MongoDB (`fetch_github_prs.py` and `fetch_github_data.py`), then execute `python -m processing_pipeline.keyword_matching.extract_from_pr` to extract energy keyword matches.
4. **Source Code/Doc Keyword Matching**: Locally clone the chosen repositories into `.tmp/source/`, then run `python -m processing_pipeline.keyword_matching.extract_from_source_code` to search for keywords in comments and documentation.

For more details, consult the [RQ1 README](./RQ1/energypattern-keyword-search/README.md) in the energypattern keyword search folder.

### Replicating RQ2: Energy Experiments
**Note:** Full replication of the experiment execution is only possible with a deployed application and a ready setup.
1. **Application Deployment**: Deploy the target applications, Mealie and Frappe (without Docker) on your server, and set up a database for them.
2. **Frappe/ERPNext Experiments**: Run the orchestrator script:
   ```bash
   python run_frappe_measurements.py
   ```
3. **Mealie Experiments**: Run the orchestrator script:
   ```bash
   python run_all_mealie_measurements.py
   ```
4. **Analysis**: Run the analysis scripts in `results_analysis` to reproduce the plots and tables.

For more details on the experimental setup, file swapping, and Scaphandre measurement library, consult the [RQ2 README](./RQ2/README.md).

### Replicating RQ3: Tool Validation
1. **Setup**: Activate your Python virtual environment and install the required dependencies (`pip install -r requirements.txt`).
2. **Run the Tool**: Get the antipattern detector tool running as described in the [RQ3 README](./RQ3/energypattern-LLM-tool/README.
md).
3. **Validate**: Input the provided test inputs in RQ3/energypattern-LLM-tool/test_inputs into the tool to analyze the source code and validate the detection and classification of energy antipatterns.

For more details on the tool's architecture, configuration and implementation details consult the [RQ3 README](./RQ3/energypattern-LLM-tool/README.md) in the tool folder.
