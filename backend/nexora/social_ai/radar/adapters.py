"""Resmî X v2 ve Telegram Bot API adaptörleri. Kimlik bilgileri açıkça enjekte edilir."""
import hmac
import json
import re
import time
from dataclasses import dataclass, field, replace
from http.client import HTTPException
from threading import RLock
from types import MappingProxyType
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from nexora.olcum import sayi, zaman

from ..providers import MAX_AGE
from .observations import chat_id, handle_matches, native_telegram, native_x, obj, post_id
from .sources import CATALOG, DELAYED, LIVE, NO_ACCESS, OK, QUOTA, UNAVAILABLE, UNKNOWN, SourceBatch

X_HOST = "https://api.x.com"
TELEGRAM_HOST = "https://api.telegram.org"
POSTS_PER_PAGE = 10
POST_COST = 5_000  # millionths of USD, estimated using X's published resource pricing
USER_COST = 10_000
CACHE_SECONDS = 60
RETENTION_SECONDS = 24 * 60 * 60
_TG_TOKEN = re.compile(r"[0-9]+:[A-Za-z0-9_-]{1,200}")
_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{1,256}")
_BEARER = re.compile(r"[A-Za-z0-9_+./%~=-]{1,4096}")


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


@dataclass(frozen=True)
class LiveOptions:
    SOCIAL_LIVE_ENABLED: bool = False
    x_daily_budget_microusd: int = 0
    x_recent_search: bool = False


@dataclass(frozen=True)
class SourceGrant:
    """An operator-reviewed binding between a catalog entry and a stable account id."""
    account_id: str
    controller: str | None = None
    read_allowed: bool = False


@dataclass(frozen=True)
class Credentials:
    x_bearer: str = field(default="", repr=False)
    telegram_token: str = field(default="", repr=False)
    telegram_webhook_secret: str = field(default="", repr=False)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    data: dict


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_get(url, params, headers):
    """Single GET with redirects and environment-provided proxies disabled."""
    request = Request(f"{url}?{urlencode(params)}" if params else url, headers=headers, method="GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            raw = response.read(2_000_001)
            data = json.loads(raw) if len(raw) <= 2_000_000 else None
            return Response(response.status, dict(response.headers), obj(data))
    except HTTPError as exc:
        try:
            return Response(exc.code, dict(exc.headers or {}), {})
        finally:
            exc.close()
    except (OSError, HTTPException, ValueError, RecursionError):
        return Response(0, {}, {})


@dataclass
class _State:
    health: SourceBatch = field(default_factory=SourceBatch)
    cache: dict = field(default_factory=dict)
    requests_used: int = 0
    cost_microusd: int = 0
    day: int | None = None
    next_poll: float = 0
    since_id: str | None = None
    high_id: str | None = None
    page: str | None = None
    telegram_admin: bool = False

    def today(self, now):
        day = int(now // 86400)
        if self.day is None or day > self.day:
            self.day, self.requests_used, self.cost_microusd = day, 0, 0

    def update_cache(self, items, now):
        self.cache = {key: item for key, item in self.cache.items()
                      if item.event.observed_at >= now - RETENTION_SECONDS}
        for item in items:
            if item.event.event_id not in self.cache:
                self.cache[item.event.event_id] = item
                event = item.event
                self.health = replace(self.health, last_seen=event.observed_at,
                                      lag_seconds=event.observed_at - (item.origin_published_at or event.published_at))

    def result(self, now, retry_at=None):
        self.today(now)
        self.update_cache((), now)
        visible = self.health.status != NO_ACCESS
        return replace(self.health, items=tuple(self.cache.values()) if visible else (),
                       requests_used=self.requests_used, cost_microusd=self.cost_microusd,
                       retry_at=max(self.health.retry_at or 0, retry_at or 0) or None)


class AuthorizedSources:
    """Collector with synchronized in-memory checkpoints, replay cache and daily limits."""
    def __init__(self, options=None, credentials=None, grants=None, *, transport=http_get, clock=time.time):
        self.options = options or LiveOptions()
        self.credentials = credentials or Credentials()
        self.grants = MappingProxyType(dict(grants or {}))
        self.transport, self.clock = transport, clock
        self.states = {source_id: _State() for source_id in CATALOG}
        self.backoff = {}
        self.strikes = {}
        self.x_day = None
        self.x_spent = 0
        self.bot_id = None
        self.lock = RLock()

    def _grant(self, source):
        grant = self.grants.get(source.source_id)
        if not isinstance(grant, SourceGrant) or grant.read_allowed is not True:
            return None
        if source.platform == "x":
            account = post_id(grant.account_id)
            has_credentials = _matches(_BEARER, self.credentials.x_bearer)
        else:
            account = chat_id(grant.account_id)
            has_credentials = (_matches(_TG_TOKEN, self.credentials.telegram_token)
                               and _matches(_WEBHOOK_SECRET, self.credentials.telegram_webhook_secret))
        return replace(grant, account_id=account) if account and has_credentials else None

    def _state(self, source):
        return self.states[source.source_id]

    def _mark(self, source, now, status, *, trust=None, retry_at=None, rejected=(), verified=None, complete=False):
        state = self._state(source)
        old = state.health
        state.health = replace(
            old,
            status=status, access_mode=UNAVAILABLE if status == NO_ACCESS else LIVE,
            trust_status=trust or old.trust_status, enabled=True, last_checked=now,
            failure_count=old.failure_count + (status not in (OK, DELAYED)), retry_at=retry_at,
            rejected=old.rejected + tuple(rejected), live_verified=old.live_verified if verified is None else verified,
            coverage_from=(old.coverage_from or now) if complete else old.coverage_from,
            coverage_until=now if complete else old.coverage_until,
        )
        if status == NO_ACCESS:
            state.cache.clear()
            state.since_id = state.high_id = state.page = None
            state.telegram_admin = False
            state.health = replace(state.health, coverage_from=None, coverage_until=None, live_verified=False,
                                   last_seen=None, lag_seconds=None)
        state.next_poll = max(state.next_poll, retry_at or 0, now + CACHE_SECONDS)

    def _get(self, source, url, params, headers, *, estimated=0):
        now = self.clock()
        state = self._state(source)
        state.today(now)
        platform = source.platform
        day = int(now // 86400)
        if self.x_day is None or day > self.x_day:
            self.x_day, self.x_spent = day, 0
        if now < self.backoff.get(platform, 0):
            self._mark(source, now, QUOTA, retry_at=self.backoff[platform])
            return None
        if state.requests_used >= source.rate_budget or (estimated and
                self.x_spent + estimated > self.options.x_daily_budget_microusd):
            self._mark(source, now, QUOTA, retry_at=(day + 1) * 86400)
            return None
        state.requests_used += 1
        try:
            response = self.transport(url, params, headers)
        except (OSError, HTTPException, ValueError, RecursionError):
            response = Response(0, {}, {})
        fetched = self.clock()
        data = obj(response.data)
        code = response.status if data.get("ok") is not False else data.get("error_code", response.status)
        if code == 429:
            self.strikes[platform] = self.strikes.get(platform, 0) + 1
            header = {k.lower(): v for k, v in response.headers.items()}
            delays = [sayi(header.get("retry-after")), sayi(obj(data.get("parameters")).get("retry_after"))]
            reset = zaman(header.get("x-rate-limit-reset"))
            if reset is not None:
                delays.append(reset - fetched)
            backoff = min(3600, CACHE_SECONDS * 2 ** min(6, self.strikes[platform] - 1))
            retry_at = fetched + max(backoff, *(value or 0 for value in delays))
            self.backoff[platform] = retry_at
            self._mark(source, fetched, QUOTA, retry_at=retry_at)
            return None
        if code in (401, 403, 404):
            self._mark(source, fetched, NO_ACCESS, trust="blocked")
            return None
        if code == 402:
            self._mark(source, fetched, QUOTA, retry_at=(day + 1) * 86400)
            return None
        if code != 200 or not data or data.get("ok") is False:
            if code == 400 and platform == "x" and "pagination_token" in params:
                state.page = state.high_id = None
            # Conservatively reserve the ceiling when billing cannot be inferred from the response.
            state.cost_microusd += estimated
            self.x_spent += estimated
            self._mark(source, fetched, UNKNOWN)
            return None
        if estimated:
            resources = data.get("data")
            cost = (POST_COST * len(resources) if estimated != USER_COST and isinstance(resources, list)
                    else USER_COST if estimated == USER_COST and isinstance(resources, dict)
                    else 0 if obj(data.get("meta")).get("result_count") == 0 else estimated)
            state.cost_microusd += cost
            self.x_spent += cost
        return data, fetched

    def _read_x(self, source, grant):
        if type(self.options.x_daily_budget_microusd) is not int or self.options.x_daily_budget_microusd < 0:
            self._mark(source, self.clock(), NO_ACCESS)
            return
        headers = {"Authorization": f"Bearer {self.credentials.x_bearer}"}
        user = self._get(source, f"{X_HOST}/2/users/by/username/{source.handle[1:]}", {}, headers, estimated=USER_COST)
        if user is None:
            return
        data, fetched = user
        identity = obj(data.get("data"))
        if identity.get("id") != grant.account_id or not handle_matches(identity.get("username"), source.handle):
            self._mark(source, fetched, NO_ACCESS, trust="blocked", rejected=("HESAP_KIMLIGI_UYUSMUYOR",))
            return
        state = self._state(source)
        recent_search = self.options.x_recent_search is True
        mode_path = "/2/tweets/search/recent" if recent_search else f"/2/users/{grant.account_id}/tweets"
        params = {
            "max_results": POSTS_PER_PAGE,
            "tweet.fields": "created_at,author_id,referenced_tweets,paid_partnership,public_metrics",
        }
        if recent_search:
            params["query"] = f"from:{source.handle[1:]}"
        if state.since_id:
            params["since_id"] = state.since_id
        if state.page:
            params["pagination_token"] = state.page
        page = self._get(source, X_HOST + mode_path, params, headers, estimated=POSTS_PER_PAGE * POST_COST)
        if page is None:
            return
        data, fetched = page
        meta = obj(data.get("meta"))
        rows = data.get("data", [] if meta.get("result_count") == 0 else None)
        next_page = meta.get("next_token")
        if (not isinstance(rows, list) or len(rows) > POSTS_PER_PAGE or data.get("errors")
                or (next_page is not None and (not isinstance(next_page, str)
                    or not 0 < len(next_page) <= 2048 or next_page == state.page))):
            self._mark(source, fetched, UNKNOWN)
            return
        observed = self.clock()
        items, rejected, ids = [], [], []
        for row in rows:
            item, error = native_x(source, row, fetched, observed, identity=grant.account_id,
                                   controller=grant.controller)
            if item is not None:
                items.append(item)
            else:
                rejected.append(error)
            if pid := post_id(obj(row).get("id")):
                ids.append(pid)
        if rows and not items:
            self._mark(source, observed, UNKNOWN, trust="verified", rejected=rejected)
            return
        state.update_cache(items, observed)
        high = max(ids + [state.high_id or state.since_id or "0"], key=int)
        state.page, state.high_id = next_page, high if high != "0" else None
        if not next_page:
            state.since_id, state.high_id = state.high_id, None
        self.strikes.pop(source.platform, None)
        self._mark(source, observed, DELAYED if next_page else OK, trust="verified",
                   rejected=rejected, verified=bool(items) or state.health.live_verified, complete=not next_page)

    def _check_telegram(self, source, grant):
        state = self._state(source)
        state.telegram_admin = False
        base = f"{TELEGRAM_HOST}/bot{self.credentials.telegram_token}"
        if self.bot_id is None:
            bot = self._get(source, f"{base}/getMe", {}, {})
            if bot is None:
                return
            user = obj(bot[0].get("result"))
            if user.get("is_bot") is not True or type(user.get("id")) is not int or user["id"] <= 0:
                self._mark(source, self.clock(), NO_ACCESS, trust="blocked")
                return
            self.bot_id = user["id"]
        channel = self._get(source, f"{base}/getChat", {"chat_id": grant.account_id}, {})
        if channel is None:
            return
        chat = obj(channel[0].get("result"))
        if (chat_id(chat.get("id")) != grant.account_id or chat.get("type") != "channel"
                or not handle_matches(chat.get("username"), source.handle)):
            self._mark(source, self.clock(), NO_ACCESS, trust="blocked", rejected=("HESAP_KIMLIGI_UYUSMUYOR",))
            return
        member = self._get(source, f"{base}/getChatMember",
                           {"chat_id": grant.account_id, "user_id": self.bot_id}, {})
        if member is None:
            return
        data = obj(member[0].get("result"))
        if obj(data.get("user")).get("id") != self.bot_id or data.get("status") not in ("administrator", "creator"):
            self._mark(source, self.clock(), NO_ACCESS, trust="blocked")
            return
        state.telegram_admin = True
        self.strikes.pop(source.platform, None)
        self._mark(source, self.clock(), OK, trust="verified")

    def read(self, source_id):
        """Return the snapshot without polling either provider."""
        with self.lock:
            return self._read(source_id)

    def _read(self, source_id):
        source = CATALOG[source_id]
        if self.options.SOCIAL_LIVE_ENABLED is not True or self._grant(source) is None:
            return SourceBatch(status=NO_ACCESS)
        now = self.clock()
        state = self._state(source)
        retry = self.backoff.get(source.platform, 0)
        result = state.result(now, retry if retry > now else None)
        if retry > now and result.status != NO_ACCESS:
            return replace(result, status=QUOTA, enabled=True)
        return replace(result, enabled=True)

    def poll(self, source_id):
        """Explicit source check. X reads one page; Telegram verifies webhook eligibility."""
        with self.lock:
            return self._poll(source_id)

    def _poll(self, source_id):
        source = CATALOG[source_id]
        if self.options.SOCIAL_LIVE_ENABLED is not True:
            return SourceBatch(status=NO_ACCESS)
        grant = self._grant(source)
        if grant is None:
            return SourceBatch(status=NO_ACCESS)
        now = self.clock()
        state = self._state(source)
        if now >= state.next_poll:
            if source.platform == "x":
                self._read_x(source, grant)
            else:
                self._check_telegram(source, grant)
        return self._read(source_id)

    def ingest_telegram(self, update, webhook_secret):
        """Accept only authenticated Bot API channel_post deliveries for approved, verified channels."""
        with self.lock:
            return self._ingest_telegram(update, webhook_secret)

    def _ingest_telegram(self, update, webhook_secret):
        received = self.clock()
        configured = self.credentials.telegram_webhook_secret
        if (self.options.SOCIAL_LIVE_ENABLED is not True or not _matches(_WEBHOOK_SECRET, webhook_secret)
                or not _matches(_WEBHOOK_SECRET, configured)
                or not hmac.compare_digest(webhook_secret, configured)):
            return None
        post = obj(obj(update).get("channel_post"))
        identity = chat_id(obj(post.get("chat")).get("id"))
        if identity is None:
            return None
        for source in CATALOG.values():
            if source.platform != "telegram":
                continue
            grant = self._grant(source)
            if grant is None or grant.account_id != identity:
                continue
            status = self._poll(source.source_id)
            state = self._state(source)
            if status.status != OK or not state.telegram_admin:
                return None
            observed = self.clock()
            item, error = native_telegram(source, post, received, observed, identity=identity,
                                          controller=grant.controller)
            if error:
                state.health = replace(state.health, rejected=state.health.rejected + (error,))
                return None
            state.update_cache((item,), observed)
            first = state.cache[item.event.event_id]
            state.health = replace(state.health, live_verified=True, coverage_from=state.health.coverage_from
                                   or first.event.observed_at,
                                   coverage_until=max(state.health.coverage_until or 0, first.event.observed_at))
            return first
        return None
