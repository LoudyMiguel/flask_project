"""Thin client for the Go backend. Every call the web app makes goes through here."""
import json

import requests
from flask import current_app, session


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _message(resp):
    """Go replies with plain text (http.Error) or JSON ({"error"|"message": ...})."""
    text = resp.text.strip()
    try:
        body = json.loads(text)
    except ValueError:
        return text or f"The server answered with status {resp.status_code}."
    if isinstance(body, dict):
        return body.get("error") or body.get("message") or text
    if isinstance(body, str):
        return body
    return text


class GoApi:
    def __init__(self, base_url, timeout):
        self.base_url = base_url
        self.timeout = timeout
        self.http = requests.Session()

    def request(self, method, path, *, token=None, params=None, json_body=None, stream=False):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.http.request(
                method,
                self.base_url + path,
                params=params,
                json=json_body,
                headers=headers,
                timeout=self.timeout,
                stream=stream,
            )
        except requests.ConnectionError:
            raise ApiError(503, "MarketFlow can't reach its server right now. Try again in a moment.")
        except requests.Timeout:
            raise ApiError(504, "The MarketFlow server took too long to answer. Try again.")

        if resp.status_code >= 400:
            message = _message(resp)
            resp.close()
            raise ApiError(resp.status_code, message)
        if stream:
            return resp
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"_text": resp.text}


def go(method, path, *, auth=True, **kwargs):
    """Call the Go API as the logged-in user."""
    client = current_app.extensions["go_api"]
    token = session.get("token") if auth else None
    if "json" in kwargs:
        kwargs["json_body"] = kwargs.pop("json")
    return client.request(method, path, token=token, **kwargs)
