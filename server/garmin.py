"""Garmin Connect Personal API, using Garmin's officially documented endpoints.

Keep credentials only in this server module: never return API keys or bearer tokens
through dashboard responses or logs.
"""
from __future__ import annotations
import base64
import json
import time
import requests
from .storage import get_key

BASE = 'https://personal.connectapi.garmin.com'
TOKEN_PATH = '/personalapitoken-service/personal-api/personal-api-key/token'

class GarminAPIError(Exception):
    pass

class GarminPersonal:
    def __init__(self, key=None):
        self.key = key if key is not None else get_key()
        if not self.key:
            raise GarminAPIError('No Garmin Personal API key is configured.')
        self.session = requests.Session()
        self.token = None
        self.expiry = 0

    def access_token(self, force=False):
        """Exchange a Personal API key for Garmin's *plain-text JWT*.

        Garmin's official reference client expects a raw JWT response, not a
        JSON object. JSON-string and object representations are also tolerated
        for compatibility with proxies and future API variants.
        """
        if self.token and not force and self.expiry > time.time() + 300:
            return self.token
        try:
            response = self.session.post(
                BASE + TOKEN_PATH,
                headers={'Authorization': 'ApiKey ' + self.key},
                timeout=25,
            )
        except requests.RequestException as exc:
            raise GarminAPIError('Could not contact Garmin to validate your key. Check the connection and try again.') from exc

        if response.status_code in (400, 401):
            raise GarminAPIError('Garmin rejected the key (HTTP %s). Confirm it is an active Garmin Connect Personal API key, not an OAuth token or a developer-app client secret.' % response.status_code)
        if response.status_code == 403:
            raise GarminAPIError('Garmin denied access (HTTP 403). Check the Personal API key status and account permissions.')
        if response.status_code == 429:
            raise GarminAPIError('Garmin is rate-limiting requests (HTTP 429). Try again later; this does not mean the key is invalid.')
        if response.status_code >= 500:
            raise GarminAPIError('Garmin authentication service is temporarily unavailable (HTTP %s). Your key has not been shown to be invalid.' % response.status_code)
        if not response.ok:
            raise GarminAPIError('Garmin token endpoint returned HTTP %s. The dashboard cannot determine key validity from this response.' % response.status_code)

        raw = response.text.strip()
        if not raw:
            raise GarminAPIError('Garmin returned an empty token response; please retry.')
        ttl = 86400
        if raw.startswith(('{', '"')):
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                raise GarminAPIError('Garmin token response was not a recognised JWT or JSON token.') from exc
            if isinstance(payload, dict):
                token = payload.get('access_token') or payload.get('accessToken')
                try:
                    ttl = int(payload.get('expires_in') or payload.get('expiresIn') or ttl)
                except (TypeError, ValueError):
                    ttl = 86400
            elif isinstance(payload, str):
                token = payload
            else:
                token = None
        else:
            token = raw

        if not isinstance(token, str) or not token.strip():
            raise GarminAPIError('Garmin returned a success response without an access token.')
        token = token.strip()
        # JWT expiry is used as an untrusted cache hint, never as a substitute
        # for Garmin's server-side authorization verification.
        sections = token.split('.')
        if len(sections) != 3:
            raise GarminAPIError('Garmin token response did not contain a valid JWT format.')
        try:
            claims = json.loads(base64.urlsafe_b64decode(sections[1] + '=' * (-len(sections[1]) % 4)))
            exp = float(claims['exp'])
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            raise GarminAPIError('Garmin supplied a token without a readable JWT expiry.') from exc
        remaining = exp - time.time()
        if remaining <= 0:
            raise GarminAPIError('Garmin supplied an already-expired token. Check the system clock and retry.')
        self.token = token
        self.expiry = time.time() + min(remaining, max(30, min(ttl, 86400)))
        return self.token

    def get(self, path, params=None, binary=False):
        if not path.startswith('/') or '://' in path:
            raise GarminAPIError('Invalid Garmin API path.')
        refreshed = False
        for attempt in range(4):
            try:
                response = self.session.get(
                    BASE + path,
                    headers={'Authorization': 'Bearer ' + self.access_token()},
                    params=params,
                    timeout=40,
                )
            except requests.RequestException as exc:
                if attempt < 3:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise GarminAPIError('Unable to reach Garmin. Check network connectivity and retry.') from exc
            if response.status_code == 401 and not refreshed:
                self.access_token(force=True)
                refreshed = True
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                retry_after = response.headers.get('Retry-After', '')
                try:
                    delay = min(30, max(1, int(retry_after)))
                except (ValueError, TypeError):
                    delay = min(2 ** (attempt + 1), 12)
                time.sleep(delay)
                continue
            if not response.ok:
                raise GarminAPIError(f'Garmin request failed (HTTP {response.status_code}) for {path}.')
            if binary:
                return response.content
            try:
                return response.json() if response.content else None
            except ValueError as exc:
                raise GarminAPIError(f'Garmin returned invalid JSON for {path}.') from exc
        raise GarminAPIError(f'Garmin request failed after retries for {path}.')

    def activities(self, start=0, limit=100):
        return self.get('/activitylist-service/activities/search/activities', {'start': start, 'limit': limit})

    def activity_zip(self, activity_id):
        return self.get(f'/download-service/files/activity/{int(activity_id)}', binary=True)

    def profile(self):
        return self.get('/userprofile-service/userprofile/settings')

    def hr_zones(self):
        return self.get('/biometric-service/heartRateZones/v2')

    def hrv(self, start, end):
        return self.get(f'/hrv-service/hrv/daily/{start}/{end}')

    def sleep(self, start, end):
        return self.get('/sleep-service/sleep/dailySleepSummariesByDate', {'startDate': start, 'endDate': end})
