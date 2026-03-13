# cjdata CLI

## Installation
```powershell
pip install .[all]
# or install the base package
pip install .
```

To build from source with version tags, ensure `setuptools-scm` is available:
```powershell
pip install setuptools-scm
```

## Commands

### Download (initial bootstrap)
```powershell
cjdata download --db path\to\data.db --start-date 20080101 --end-date 20251110
```
This pulls xtquant reference data plus baostock daily bars into the SQLite database.

Options:
- `--start-date` — Start date in `YYYYMMDD` format (default: `20080101`)
- `--end-date` — End date in `YYYYMMDD` format (default: today)
- `--skip-xtquant` — Skip the xtquant stage
- `--skip-baostock` — Skip the baostock stage
- `--skip-daily` — Skip ETF and stock daily market data downloads
- `--skip-dupont` — Skip DuPont financial metrics download
- `--only-dupont` — Only download DuPont data (equivalent to `--skip-xtquant --skip-daily`)
- `--smoke-test` — Only download the first 5 stocks; useful for verifying code changes without a full run

### Update (incremental refresh)
```powershell
cjdata update --db path\to\data.db --end-date 20251110
```
Fetches only new bars since the last recorded date for each stock.

Options:
- `--end-date` — End date in `YYYYMMDD` format (default: today)
- `--skip-xtquant` — Skip the xtquant stage
- `--skip-baostock` — Skip the baostock stage
- `--skip-daily` — Skip ETF and stock daily market data downloads
- `--skip-dupont` — Skip DuPont financial metrics download
- `--only-dupont` — Only update DuPont data (equivalent to `--skip-xtquant --skip-daily`)
- `--smoke-test` — Only download the first 5 stocks; useful for verifying code changes without a full run

### DuPont metrics
```powershell
cjdata download --db path\to\data.db --only-dupont --start-date 20180101 --end-date 20251110
```
By default, both daily data and DuPont metrics are downloaded. Use `--only-dupont` for a DuPont-only refresh.

### Smoke test
```powershell
cjdata download --db smoke.db --smoke-test
cjdata update --db smoke.db --smoke-test
```
Limits each pipeline to the first 5 stocks, allowing quick validation that code changes do not introduce regressions.

## Alternative invocation
You can run any command via the module entry point:
```powershell
python -m cjdata download --db path\to\data.db
```