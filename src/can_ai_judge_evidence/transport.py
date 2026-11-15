"""Single-attempt OpenAI Responses transport. No SDK or hidden retry policy."""
from dataclasses import dataclass
from http.client import HTTPException
import json
import os
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = os.environ.get('CAJE_ENDPOINT', 'https://api.openai.com/v1/responses')
RETRYABLE_HTTP = frozenset((408, 429, 500, 502, 503, 504))


@dataclass(frozen=True)
class TransportReply:
    body: bytes
    status: int = 200
    request_id: str | None = None


class TransportError(Exception):
    def __init__(self, message: str, *, retryable: bool, reply: TransportReply | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.reply = reply


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an API credential to a redirect destination.
        return None


class OpenAIResponsesTransport:
    """Only this boundary reads credentials. Logs never receive auth headers."""
    def __init__(self, *, timeout_seconds: float = 120, endpoint: str = ENDPOINT):
        self.key = os.environ.get('CAJE_API_KEY') or os.environ.get('OPENAI_API_KEY')
        if not self.key:
            raise ValueError('Set CAJE_API_KEY (or OPENAI_API_KEY) in your environment before a live run')
        if not endpoint.startswith('https://'):
            raise ValueError('endpoint must use https; credentials are never sent in clear text')
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.opener = build_opener(_NoRedirect())

    def __call__(self, payload: dict) -> TransportReply:
        request = Request(self.endpoint, data=json.dumps(payload, allow_nan=False).encode('utf-8'),
                          headers={'Authorization': f'Bearer {self.key}',
                                   'Content-Type': 'application/json'}, method='POST')
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                return TransportReply(response.read(), response.status, response.headers.get('x-request-id'))
        except HTTPError as error:
            reply = TransportReply(error.read(), error.code, error.headers.get('x-request-id'))
            raise TransportError(f'HTTP {error.code}', retryable=error.code in RETRYABLE_HTTP,
                                 reply=reply) from error
        except URLError as error:
            # Certificate verification errors need operator intervention.
            retryable = not isinstance(error.reason, ssl.SSLCertVerificationError)
            raise TransportError(type(error.reason).__name__, retryable=retryable) from error
        except (TimeoutError, socket.timeout, ConnectionError, HTTPException) as error:
            raise TransportError(type(error).__name__, retryable=True) from error
