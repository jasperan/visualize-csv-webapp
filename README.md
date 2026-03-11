# CSVViz — Instant CSV Visualization & AI Analysis

[![License: UPL](https://img.shields.io/badge/license-UPL-green)](https://img.shields.io/badge/license-UPL-green) [![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=oracle-devrel_test)](https://sonarcloud.io/dashboard?id=oracle-devrel_test)

Upload any CSV file and get **interactive charts**, **auto-detected insights**, and **AI-powered natural language analysis** — all in your browser.

## Features

- **Drag-and-drop upload** with progress indicator and file validation
- **Auto-generated Plotly charts** — histograms, scatter plots, bar charts, box plots, time series, and correlation heatmaps selected automatically based on your data's column types
- **Smart insight cards** — outliers (IQR), strong correlations, skewed distributions, missing data patterns, duplicates, and high-cardinality warnings detected on upload
- **Interactive data table** — sortable columns, pagination, and a column picker sidebar to show/hide fields
- **"Chat with your CSV"** — ask natural language questions about your data (powered by Ollama); the AI writes and executes Pandas code, returning answers, tables, and charts
- **Dark mode** — automatic system preference detection with manual toggle
- **Summary statistics** — per-column count, mean, std, min, median, max, and unique values
- **REST API** — all data, insights, charts, and stats available as JSON endpoints

## Quick Start

```bash
# Clone and install
git clone https://github.com/jasperan/visualize-csv-webapp.git
cd visualize-csv-webapp
pip install -r requirements.txt

# Run
python app.py
```

Open [http://localhost:5000](http://localhost:5000) and drop a CSV file.

### AI Chat (optional)

To enable the "Chat with your CSV" feature, install and run [Ollama](https://ollama.com/):

```bash
ollama pull qwen3.5:latest
# The app auto-connects to Ollama on localhost:11434
```

Configure via environment variables:

```bash
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:latest
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data` | GET | Paginated table data (`?page=1&per_page=50`) |
| `/api/column_info` | GET | Column names, types, null percentages |
| `/api/insights` | GET | Auto-detected data insights |
| `/api/charts` | GET | Auto-suggested Plotly chart configs |
| `/api/stats` | GET | Summary statistics per column |
| `/api/chat` | POST | Natural language question (JSON: `{"question": "..."}`) |
| `/api/ollama/status` | GET | Check Ollama availability |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Tech Stack

- **Backend**: Python, Flask, Pandas, NumPy
- **Frontend**: TailwindCSS (CDN), Plotly.js
- **AI**: Ollama (local LLM inference)

## Contributing

This project is open source. Please submit your contributions by forking this repository and submitting a pull request! Oracle appreciates any contributions that are made by the open source community.

## License

Copyright (c) 2022 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](LICENSE) for more details.

ORACLE AND ITS AFFILIATES DO NOT PROVIDE ANY WARRANTY WHATSOEVER, EXPRESS OR IMPLIED, FOR ANY SOFTWARE, MATERIAL OR CONTENT OF ANY KIND CONTAINED OR PRODUCED WITHIN THIS REPOSITORY, AND IN PARTICULAR SPECIFICALLY DISCLAIM ANY AND ALL IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, AND FITNESS FOR A PARTICULAR PURPOSE. FURTHERMORE, ORACLE AND ITS AFFILIATES DO NOT REPRESENT THAT ANY CUSTOMARY SECURITY REVIEW HAS BEEN PERFORMED WITH RESPECT TO ANY SOFTWARE, MATERIAL OR CONTENT CONTAINED OR PRODUCED WITHIN THIS REPOSITORY. IN ADDITION, AND WITHOUT LIMITING THE FOREGOING, THIRD PARTIES MAY HAVE POSTED SOFTWARE, MATERIAL OR CONTENT TO THIS REPOSITORY WITHOUT ANY REVIEW. USE AT YOUR OWN RISK.
