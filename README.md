# Manus Clone

Manus Clone performs smart web research using an LLM, selectively scrapes LinkedIn profiles when present, and produces a clean, text-only report. It can be used from a web UI or CLI.

## How it works

- Query classification: routes fact-style questions to web-only search; routes LinkedIn requests to profile scraping.
- Web search (Compound-Beta): returns a narrative Answer and per-link title/url/snippet; also captures LinkedIn profile links.
- LinkedIn scraping: if profile URLs appear, a Playwright-based scraper extracts profile data.
- Reporting: generates a text-only report with Query context, Executive summary, Core Data (LinkedIn table if present, Web sources table otherwise), and Sources.

Components: Task executor (search + optional scraping), task updater (progress/logging), report generator (LLM + Jinja2 template).

## Quick start

Requirements

- Python 3.12+
- .env with GROQ_API_KEY; optionally LINKEDIN_EMAIL and LINKEDIN_PASSWORD

Install

```bash
pip install -r requirements.txt
playwright install chromium
```

### Run (CLI)

```bash
# Basic usage
python main.py -i "Find software engineers in San Francisco with Python skills"

# Verbose mode with detailed progress
python main.py -i "Analyze data scientists in New York" -m 20 -v

# Save results to custom file
python main.py -i "Find product managers in London" -o my_analysis.json

# Quiet mode (minimal output)
python main.py -i "Search for UI/UX designers" -q

# Show help
python main.py --help
```

### Run (Web UI)

```bash
uvicorn api_server:app --reload --port 8000
# open http://localhost:8000
```

#### Example Inputs

```bash
# Find specific roles
python main.py -i "Find senior software engineers in Seattle"

# Analyze skills
python main.py -i "Find professionals with machine learning skills in Boston"

# Geographic analysis
python main.py -i "Analyze job market for developers in Austin, Texas"

# Multiple criteria
python main.py -i "Find product managers with 5+ years experience in San Francisco Bay Area"
```

#### Demo and Examples

Try the interactive demo to see the CLI in action:

```bash
# Run the demo script
python demo_cli.py

# Or try individual examples
python example_usage.py
```

## Output

The system generates:

1. Text report: output/reports/
2. Raw search artifacts: output/raw_data/compound_beta/
3. Prepared CSV: output/cleaned_data/

### Sample Report Structure

```markdown
# Job Market Analysis Report

## Executive Summary
- Total profiles analyzed
- Key findings and insights

## Key Statistics
- Geographic distribution
- Skills analysis
- Experience levels

## AI-Powered Analysis
- Market trends
- Recommendations
- Skills gap analysis

## Visual Analysis
- Location distribution charts
- Skills frequency charts
- Experience level pie charts

## Sample Profiles
- Top matching profiles
- Detailed information
```

## Configuration

Environment variables

| Variable | Description | Required |
|----------|-------------|----------|
| GROQ_API_KEY | Groq API key | Yes |
| LINKEDIN_EMAIL | LinkedIn login email | No |
| LINKEDIN_PASSWORD | LinkedIn login password | No |

### Customization

#### Report Format
Modify `agents/report_generator.py` to customize:
- Report templates
- Analysis prompts

#### API + Frontend
Run the web UI and API server:
```bash
uvicorn api_server:app --reload --port 8000
# then open http://localhost:8000
```

#### Scraping Behavior
Modify `scrapers/linkedin_scraper.py` to customize:
- Scraping selectors
- Rate limiting
- Error handling

## 📈 Performance

### Typical Execution Times
- **Small analysis** (10-50 profiles): 2-5 minutes
- **Medium analysis** (50-200 profiles): 5-15 minutes
- **Large analysis** (200+ profiles): 15-30 minutes

### Resource Usage
- **Memory**: 500MB - 2GB depending on dataset size
- **CPU**: Moderate usage during scraping and analysis
- **Network**: High usage during web scraping phase

## Development

### Project Structure

```
manus-clone/
├── agents/                     # Agent implementations
│   ├── user_requirement_analysis.py
│   ├── task_executor.py
│   ├── task_updater.py
│   ├── api_server.py
│   └── report_generator.py
├── scrapers/                   # Web scraping modules
│   └── linkedin_scraper.py
├── main.py                     # Main orchestration
├── requirements.txt            # Dependencies
├── README.md                   # This file
└── .env                        # Environment variables
```

### Adding New Agents

1. Create new agent file in `agents/` directory
2. Implement required interface methods
3. Update main orchestration in `main.py`
4. Add to workflow sequence

### Adding New Data Sources

1. Create new scraper in `scrapers/` directory
2. Implement scraping interface
3. Update `TaskExecutorAgent` to use new scraper
4. Test with sample data

## Troubleshooting

### Common Issues

1. **Groq API Errors**
   ```bash
   # Check API key
   echo $GROQ_API_KEY
   
   # Verify quota
   # Check Groq dashboard for usage limits
   ```

2. **Scraping Failures**
   ```bash
   # Check network connectivity
   # Verify LinkedIn credentials
   # Review logs in manus_clone.log
   ```

3. **Memory Issues**
   ```bash
   # Reduce max_results in user input
   # Increase system memory
   # Use smaller datasets for testing
   ```

### Debug Mode

```bash
# Enable verbose logging
python main.py --input "test input" --verbose

# Check logs
tail -f manus_clone.log
```