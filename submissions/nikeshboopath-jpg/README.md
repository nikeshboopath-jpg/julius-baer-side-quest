# Transfer Utility (modernized)

This project modernizes a legacy transfer invoker and adds several safety
checks and conveniences:

- Python 3 with type hints and docstrings
- Uses `requests` for HTTP
- Logging with configurable verbosity
- Configuration via `config.ini` or environment variables
- Dry-run by default to avoid accidental network calls
- Account validation (`/accounts/validate/{id}`) before transfer
- Account balance check (`/accounts/balance/{id}`) to prevent overdrafts
- Optional JWT authentication support via `/authToken` (helper available)

This README covers setup, configuration, running the script, and testing.

## Setup

Create and activate a virtual environment, then install requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example config and edit values as needed:

```bash
cp config.ini.example config.ini
# edit config.ini to set dry_run = false and endpoint as needed
```

Config options (in `config.ini` under `[transfer]`) or via environment variables
(env vars take precedence):

- `endpoint` / `TRANSFER_ENDPOINT`: base URL for the banking API (e.g. http://localhost:8123)
- `dry_run` / `DRY_RUN`: default `true`. Set to `false` to perform actual transfers
- `timeout` / `TIMEOUT`: network timeout in seconds

Optional auth environment variables (not required):

- `AUTH_USERNAME` / `AUTH_PASSWORD` / `AUTH_CLAIM` — if you want `main()` to
  obtain a token automatically (not enabled by default).

### Using a .env file

You can place environment variables in a `.env` file at the project root for
local development. The code will load `.env` automatically if `python-dotenv`
is installed. `.env` variables behave the same as real environment variables
and override values in `config.ini`.

Create a `.env` by copying the example:

```bash
cp .env.example .env
```

Example `.env` contents (see `.env.example`):

```ini
TRANSFER_ENDPOINT=http://localhost:8123/
DRY_RUN=true
TIMEOUT=5.0
#AUTH_USERNAME=alice
#AUTH_PASSWORD=any
```

## Running the script

The script defaults to a dry-run (it will not call the transfer endpoint).
To run:

```bash
python3 invoke_transfer.py
```

To perform a real transfer:

1. Set `dry_run = false` in `config.ini` (or `DRY_RUN=false` in the environment).
2. Ensure `endpoint` points to your API (can be a base URL like `http://localhost:8123` or the full transfer URL). The code will append `/transfer` if needed.

## Programmatic usage

You can call `transfer_money()` from your code. Example (with optional token):

```py
from invoke_transfer import get_auth_token, transfer_money

base = "http://localhost:8123"
# optionally get a token if your server requires it
token = get_auth_token(base, username="alice", password="any", claim="transfer")

result = transfer_money("ACC1000", "ACC1001", 150.0, endpoint=base, auth_token=token)
print(result)
```

Behavior summary:
- Before performing the transfer the code validates both accounts via `/accounts/validate/{id}`.
- It fetches the source account balance via `/accounts/balance/{id}` and returns a structured failure if funds are insufficient:

```json
{"status":"FAILED","message":"Insufficient funds","availableBalance":1000.0,"requestedAmount":1500.0}
```

## Tests

Unit tests use `pytest` and are located under `tests/`.

Run tests with the project's Python environment:

```bash
source .venv/bin/activate
.venv/bin/python -m pytest -q
```

The test suite uses `monkeypatch` to mock `requests.get` and `requests.post` and covers:
- successful transfer flow
- insufficient funds (transfer is not called)
- invalid account (transfer is not called)

## Notes and best practices

- Keep `config.ini` out of version control if it contains secrets (it's ignored by `.gitignore`). Use environment variables in CI instead.
- The code accepts either a base `endpoint` or a full `/transfer` URL. When given a base URL the client will append `/transfer` for the POST and use base + `/accounts/...` for account calls.
- For production use consider adding retry/backoff logic, structured logging (JSON), and stricter error/exception handling.
- You can add a CI workflow (GitHub Actions) to run pytest on PRs — I can add an example if you want.

## Troubleshooting

- If tests do not run, ensure you installed `pytest` into the same virtual environment and activated it.
- To debug network calls, set `logger.setLevel(logging.DEBUG)` in `invoke_transfer.py` or run with `PYTHONWARNINGS`/env vars as appropriate.

## Contact

If you need help wiring authentication or CI, tell me which option you'd like and I can add it.
