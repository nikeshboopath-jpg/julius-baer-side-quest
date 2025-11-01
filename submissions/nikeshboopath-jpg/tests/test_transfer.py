import json
from types import SimpleNamespace

import pytest

from invoke_transfer import transfer_money


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text_data="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text_data
        self.headers = headers or {"Content-Type": "application/json"}

    def raise_for_status(self):
        if 400 <= self.status_code:
            # emulate requests.exceptions.HTTPError that has a response attribute
            err = Exception(f"{self.status_code} Error")
            import pytest

            from legacy_transfer_invoke import transfer_money


            class DummyResponse:
                def __init__(self, status_code=200, json_data=None, text_data="", headers=None):
                    self.status_code = status_code
                    self._json = json_data
                    self.text = text_data
                    self.headers = headers or {"Content-Type": "application/json"}

                def raise_for_status(self):
                    if 400 <= self.status_code:
                        # emulate requests.exceptions.HTTPError that has a response attribute
                        err = Exception(f"{self.status_code} Error")
                        err.response = self
                        raise err

                def json(self):
                    if self._json is None:
                        raise ValueError("No JSON")
                    return self._json


            def test_transfer_money_success(monkeypatch):
                # Arrange: create a dummy successful JSON response
                expected = {"status": "ok", "id": "tx123"}
                resp = DummyResponse(status_code=200, json_data=expected)

                def fake_post(url, json, timeout):
                    # validate payload shape a little
                    assert "fromAccount" in json and "toAccount" in json and "amount" in json
                    return resp

                monkeypatch.setattr("legacy_transfer_invoke.requests.post", fake_post)

                # Act
                result = transfer_money("A", "B", 12.34, endpoint="http://example", timeout=1.0)

                # Assert
                assert result == expected
import pytest

from invoke_transfer import transfer_money


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text_data="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text_data
        self.headers = headers or {"Content-Type": "application/json"}

    def raise_for_status(self):
        if 400 <= self.status_code:
            err = Exception(f"{self.status_code} Error")
            err.response = self
            raise err

    def json(self):
        if self._json is None:
            raise ValueError("No JSON")
        return self._json


def test_transfer_success(monkeypatch):
    # Arrange: validate both accounts and return a sufficient balance, then a successful transfer
    def fake_get(url, headers=None, timeout=None):
        if "/accounts/validate/" in url:
            return DummyResponse(status_code=200, json_data={})
        if "/accounts/balance/" in url:
            return DummyResponse(status_code=200, json_data={"id": "ACC1000", "balance": 1000.0})
        raise AssertionError("Unexpected GET URL: %s" % url)

    def fake_post(url, json=None, headers=None, timeout=None):
        if url.rstrip('/').endswith('/transfer'):
            return DummyResponse(status_code=200, json_data={"transactionId": "tx123", "status": "SUCCESS"})
        raise AssertionError("Unexpected POST URL: %s" % url)

    monkeypatch.setattr("invoke_transfer.requests.get", fake_get)
    monkeypatch.setattr("invoke_transfer.requests.post", fake_post)

    # Act
    result = transfer_money("ACC1000", "ACC1001", 100.0, endpoint="http://example", timeout=1.0)

    # Assert
    assert isinstance(result, dict)
    assert result.get("status") == "SUCCESS"


def test_transfer_insufficient_funds(monkeypatch):
    # Arrange: accounts validate but balance is too low
    def fake_get(url, headers=None, timeout=None):
        if "/accounts/validate/" in url:
            return DummyResponse(status_code=200, json_data={})
        if "/accounts/balance/" in url:
            return DummyResponse(status_code=200, json_data={"id": "ACC1000", "balance": 50.0})
        raise AssertionError("Unexpected GET URL: %s" % url)

    def fake_post_should_not_be_called(url, json=None, headers=None, timeout=None):
        raise AssertionError("Transfer POST should not be called on insufficient funds")

    monkeypatch.setattr("invoke_transfer.requests.get", fake_get)
    monkeypatch.setattr("invoke_transfer.requests.post", fake_post_should_not_be_called)

    # Act
    result = transfer_money("ACC1000", "ACC1001", 100.0, endpoint="http://example", timeout=1.0)

    # Assert - we return a structured failure object indicating insufficient funds
    assert isinstance(result, dict)
    assert result.get("status") == "FAILED"
    assert "availableBalance" in result


def test_transfer_invalid_account(monkeypatch):
    # Arrange: source account validation fails
    def fake_get(url, headers=None, timeout=None):
        if "/accounts/validate/ACC1000" in url:
            return DummyResponse(status_code=404, json_data={})
        if "/accounts/validate/ACC1001" in url:
            return DummyResponse(status_code=200, json_data={})
        if "/accounts/balance/" in url:
            return DummyResponse(status_code=200, json_data={"id": "ACC1000", "balance": 1000.0})
        raise AssertionError("Unexpected GET URL: %s" % url)

    def fake_post_should_not_be_called(url, json=None, headers=None, timeout=None):
        raise AssertionError("Transfer POST should not be called when account invalid")

    monkeypatch.setattr("invoke_transfer.requests.get", fake_get)
    monkeypatch.setattr("invoke_transfer.requests.post", fake_post_should_not_be_called)

    # Act
    result = transfer_money("ACC1000", "ACC1001", 10.0, endpoint="http://example", timeout=1.0)

    # Assert
    assert result is None