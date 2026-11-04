# شرکت‌یاب (sherkatyab)
Keyword → Iranian companies from Rasmio (via `rasmio-mcp`), ranked, cached in the `db` branch, Excel export.
- Site: `index.html` (GitHub Pages, branch main). Needs a fine-grained token with Actions: read/write on this repo, entered once in the page.
- Search runs in `.github/workflows/company-search.yml` → `company_search.py` → `db/companies.json`, `db/searches.json`.
- Test: `PYTHONPATH=. python3 test_company.py`
