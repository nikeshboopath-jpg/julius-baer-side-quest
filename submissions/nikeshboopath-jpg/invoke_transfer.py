"""Modernized transfer utility.

Replaces legacy urllib2-based code with a modern Python 3 implementation using
the requests library, structured configuration, logging, type hints and
improved error handling. Default behavior is a dry-run to avoid accidental
network calls; toggle via config or environment.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import configparser
import requests
try:
    # optional - will be present in dev environments when configured
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional behavior
    load_dotenv = None

# Constants
# Use the base server URL as the default. The code will append paths
# (e.g. /transfer, /accounts/validate/{id}, /accounts/balance/{id}).
DEFAULT_ENDPOINT = "http://localhost:8123/"
DEFAULT_TIMEOUT = 5.0

# Setup basic logging
logger = logging.getLogger("transfer")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from a config file or environment variables.

    Priority: environment variables > config file > defaults.

    Recognized settings:
    - TRANSFER_ENDPOINT or [transfer].endpoint
    - DRY_RUN (bool) or [transfer].dry_run
    - TIMEOUT (float) or [transfer].timeout
    """
    cfg: Dict[str, Any] = {
        "endpoint": os.getenv("TRANSFER_ENDPOINT", DEFAULT_ENDPOINT),
        "dry_run": os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes"),
        "timeout": float(os.getenv("TIMEOUT", str(DEFAULT_TIMEOUT))),
    }

    # Load .env file if python-dotenv is installed. This populates os.environ
    # from a local .env file (useful in dev and CI). Environment variables
    # still take precedence over config file values.
    if load_dotenv:
        try:
            load_dotenv()
        except Exception:
            # best-effort: ignore failures to avoid breaking behavior
            logger.debug("Failed to load .env file via python-dotenv")

    if not config_path:
        config_path = Path(__file__).with_name("config.ini")

    if config_path.exists():
        parser = configparser.ConfigParser()
        parser.read(config_path)
        if parser.has_section("transfer"):
            section = parser["transfer"]
            cfg["endpoint"] = os.getenv("TRANSFER_ENDPOINT", section.get("endpoint", cfg["endpoint"]))
            cfg["dry_run"] = os.getenv("DRY_RUN", section.get("dry_run", str(cfg["dry_run"]))).lower() in ("1", "true", "yes")
            cfg["timeout"] = float(os.getenv("TIMEOUT", section.get("timeout", str(cfg["timeout"]))))

    return cfg


def get_auth_token(base_url: str, username: str, password: str, claim: str = "enquiry", timeout: float = DEFAULT_TIMEOUT) -> Optional[str]:
    """Obtain a JWT token from the auth endpoint when credentials are provided.

    Returns the token string on success or None on failure.
    """
    url = f"{base_url.rstrip('/')}/authToken?claim={claim}"
    try:
        resp = requests.post(url, json={"username": username, "password": password}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Accept either {'token': '...'} or {'access_token': '...'}
        token = data.get("token") or data.get("access_token")
        if token:
            logger.info("Obtained auth token for user %s", username)
            return token
        logger.warning("Auth token response did not contain token field: %s", data)
    except requests.RequestException as exc:
        logger.error("Failed to obtain auth token: %s", exc)
    except ValueError as exc:
        logger.error("Invalid JSON in auth token response: %s", exc)

    return None


def validate_account(account_id: str, base_url: str, headers: Optional[Dict[str, str]] = None, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Check if an account is valid/active by calling /accounts/validate/{id}.

    Returns True when the account is valid (200), False otherwise.
    """
    url = f"{base_url.rstrip('/')}/accounts/validate/{account_id}"
    try:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            return True
        logger.warning("Account %s validation returned status %s", account_id, resp.status_code)
    except requests.RequestException as exc:
        logger.error("Error validating account %s: %s", account_id, exc)
    return False


def get_account_balance(account_id: str, base_url: str, headers: Optional[Dict[str, str]] = None, timeout: float = DEFAULT_TIMEOUT) -> Optional[float]:
    """Retrieve the account balance from /accounts/balance/{id}.

    Returns the balance as float on success, or None on error.
    """
    url = f"{base_url.rstrip('/')}/accounts/balance/{account_id}"
    try:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        resp.raise_for_status()
        try:
            data = resp.json()
            # Expecting {'id': 'ACC1000', 'balance': 1000.0} or similar
            if isinstance(data, dict) and ("balance" in data):
                return float(data["balance"])
            # If the API returns a bare number
            if isinstance(data, (int, float)):
                return float(data)
            logger.error("Unexpected balance response format: %s", data)
        except ValueError:
            # Not JSON, maybe plain text number
            text = resp.text.strip()
            try:
                return float(text)
            except ValueError:
                logger.error("Unable to parse balance from response text: %s", text)
    except requests.RequestException as exc:
        logger.error("Error fetching balance for %s: %s", account_id, exc)
    return None


def transfer_money(from_acc: str, to_acc: str, amount: float, endpoint: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT, auth_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Transfer money from one account to another.

    This function will POST a JSON payload to the configured endpoint and
    return the parsed JSON response when available. On errors it will log and
    return None.

    Args:
        from_acc: Source account identifier.
        to_acc: Destination account identifier.
        amount: Amount to transfer.
        endpoint: Optional HTTP endpoint to POST to. If None, the default is used.
        timeout: Network timeout in seconds.

    Returns:
        Parsed JSON response as a dict on success, or None on failure.
    """
    payload = {
        "fromAccount": from_acc,
        "toAccount": to_acc,
        "amount": amount,
    }

    if endpoint is None:
        endpoint = DEFAULT_ENDPOINT

    logger.debug("Preparing transfer: %s -> %s amount=%s to %s", from_acc, to_acc, amount, endpoint)

    headers: Dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    # Validate accounts
    if not validate_account(from_acc, endpoint or DEFAULT_ENDPOINT, headers=headers, timeout=timeout):
        logger.error("Source account %s is invalid", from_acc)
        return None
    if not validate_account(to_acc, endpoint or DEFAULT_ENDPOINT, headers=headers, timeout=timeout):
        logger.error("Destination account %s is invalid", to_acc)
        return None

    # Check balance
    balance = get_account_balance(from_acc, endpoint or DEFAULT_ENDPOINT, headers=headers, timeout=timeout)
    if balance is None:
        logger.error("Could not retrieve balance for %s", from_acc)
        return None
    if amount > balance:
        logger.warning("Insufficient funds: available=%s requested=%s", balance, amount)
        # Optionally return structured info about insufficiency
        return {"status": "FAILED", "message": "Insufficient funds", "availableBalance": balance, "requestedAmount": amount}

    try:
        # Ensure transfer POST target ends with /transfer when a base endpoint is provided
        base = (endpoint or DEFAULT_ENDPOINT).rstrip('/')
        post_url = base if base.endswith('/transfer') else f"{base}/transfer"
        response = requests.post(post_url, json=payload, headers=headers or None, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            result = response.json()
        else:
            result = {"text": response.text}

        logger.info("Transfer successful: %s", result)
        return result

    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP error during transfer: %s - %s", exc, getattr(exc.response, "text", ""))
    except requests.exceptions.RequestException as exc:
        logger.error("Network error during transfer: %s", exc)
    except ValueError as exc:
        # JSON decoding errors
        logger.error("Failed to decode response: %s", exc)

    return None


def main() -> None:
    """CLI entry point for a quick manual transfer run.

    By default the script runs in dry-run mode (no network calls) unless the
    configuration sets dry_run = false.
    """
    cfg = load_config()
    endpoint = cfg.get("endpoint", DEFAULT_ENDPOINT)
    dry_run = bool(cfg.get("dry_run", True))
    timeout = float(cfg.get("timeout", DEFAULT_TIMEOUT))

    # Example values for a quick demo — in real usage these would come from
    # arguments, environment, or another calling application.
    from_acc = "ACC1000"
    to_acc = "ACC1001"
    amount = 100.0

    logger.info("Configuration: endpoint=%s dry_run=%s timeout=%s", endpoint, dry_run, timeout)

    if dry_run:
        logger.info("Dry-run enabled — no network call will be made. Payload: %s", json.dumps({"fromAccount": from_acc, "toAccount": to_acc, "amount": amount}))
        simulated = {"status": "dry-run", "from": from_acc, "to": to_acc, "amount": amount}
        print(f"Simulated transfer result: {simulated}")
    else:
        result = transfer_money(from_acc, to_acc, amount, endpoint=endpoint, timeout=timeout)
        print(f"Transfer result: {result}")


if __name__ == "__main__":
    main()