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
cjdata download --db path\to\data.db --start-date 2008-01-01 --end-date 2025-11-10
```
This pulls xtquant reference data plus baostock daily bars into the SQLite database.

### Update (incremental refresh)
```powershell
cjdata update --db path\to\data.db --start-date 2025-11-01 --end-date 2025-11-10
```
Only the requested date range is refreshed if newer bars exist.

### Dupont metrics
```powershell
cjdata download --db path\to\data.db --dupont --start-date 2018-01-01 --end-date 2025-11-10
```
Adds or updates Dupont financial metrics alongside existing price data.

## Alternative invocation
You can run any command via the module entry point:
```powershell
python -m cjdata download --db path\to\data.db
```