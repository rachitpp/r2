"""Model providers, pacing, and the response cache.

Three things live here because they are inseparable in practice: a provider
interface, a rate limiter that keeps a free tier alive, and a cache that means
a re-run of an eval costs nothing.

**Serial, always.** RPM is the first ceiling on a free tier, so there is no
concurrency here and adding some would only make the limiter's job harder.

**No sampling parameters.** `temperature`, `top_p` and `top_k` are deprecated
and ignored on the models this project uses, and return HTTP 400 on future
generations — see ADR-0006. Sending them would look like a determinism control
while doing nothing.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pos_copilot import env

CACHE_DIR = Path(__file__).resolve().parents[3] / "evals" / ".cache"


class RateLimited(RuntimeError):
    """Provider returned 429 and the retry budget is spent."""


class BudgetExceeded(RuntimeError):
    """The run hit its call or spend ceiling and stopped itself."""


@dataclass
class Budget:
    """A hard stop on calls and estimated spend, checked before every request.

    Credits and free tiers both fail the same way: a loop that should have made
    forty calls makes four thousand, and nothing complains until the money is
    gone or the day is. The ceiling is not a safety net for a runaway loop, it
    is the thing that makes a runaway loop cheap to discover.

    Estimated, not billed. It stops obvious runaways; it is not an accountant.
    """

    max_calls: int = 250
    max_spend_usd: float = 25.0
    usd_per_million_input: float = 1.50
    usd_per_million_output: float = 7.50
    assumed_output_tokens: int = 400
    calls: int = 0
    input_tokens: int = 0

    @property
    def spend_usd(self) -> float:
        out = self.calls * self.assumed_output_tokens
        return (
            self.input_tokens / 1e6 * self.usd_per_million_input
            + out / 1e6 * self.usd_per_million_output
        )

    def check(self, next_prompt: str) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(
                f"stopped at the {self.max_calls}-call ceiling "
                f"(~${self.spend_usd:.2f} estimated). Raise --max-calls only "
                "after checking why so many were needed."
            )
        projected = self.spend_usd + len(next_prompt) / 4 / 1e6 * (
            self.usd_per_million_input
        )
        if projected > self.max_spend_usd:
            raise BudgetExceeded(
                f"stopped at the ${self.max_spend_usd:.2f} ceiling after "
                f"{self.calls} calls (~${self.spend_usd:.2f} estimated)."
            )

    def record(self, prompt: str) -> None:
        self.calls += 1
        self.input_tokens += len(prompt) // 4


@dataclass
class Pacer:
    """Serial pacing plus exponential backoff with jitter.

    `min_interval` is the floor between the *starts* of two requests, derived
    from the RPM allowance. Backoff is separate: it reacts to a 429 rather than
    trying to predict one.

    Jitter is full-range rather than a small wobble. With a serial runner
    retrying a single stream it matters less than it would with many clients,
    but it costs nothing and it stops a repeated 429 producing a metronome.
    """

    rpm: int = 10
    max_attempts: int = 6
    base_delay: float = 2.0
    max_delay: float = 120.0
    seed: int = 42
    _rng: random.Random = field(init=False, repr=False)
    # None, not 0.0: a clock reading of exactly zero is a legitimate first
    # timestamp, and a falsy sentinel would silently disable pacing for it.
    _last_start: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    @property
    def min_interval(self) -> float:
        return 60.0 / max(1, self.rpm)

    def wait_turn(self, sleep=time.sleep, clock=time.monotonic) -> None:
        if self._last_start is not None:
            elapsed = clock() - self._last_start
            if elapsed < self.min_interval:
                sleep(self.min_interval - elapsed)
        self._last_start = clock()

    def backoff_delay(self, attempt: int) -> float:
        """Full-jitter exponential backoff, capped."""
        ceiling = min(self.max_delay, self.base_delay * (2**attempt))
        return self._rng.uniform(0.0, ceiling)


class Provider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str) -> str: ...


@dataclass
class StubProvider:
    """Answers from a fixed table. No network, no key, no quota.

    The runner is built and exercised against this before a real key is used,
    so plumbing bugs cost nothing to find.
    """

    responses: dict[str, str]
    default: str = "-- INSUFFICIENT SCHEMA: stub has no answer for this"
    name: str = "stub"
    model: str = "stub-v1"
    calls: list[str] = field(default_factory=list)

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        for key, response in self.responses.items():
            if key in prompt:
                return response
        return self.default


@dataclass
class GeminiProvider:
    """Google Gemini via the REST API.

    Deliberately no `generationConfig` sampling fields: they are ignored on
    these models today and error on later ones (ADR-0006).
    """

    model: str
    api_key: str
    pacer: Pacer = field(default_factory=Pacer)
    name: str = "gemini"
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models"

    def generate(self, prompt: str) -> str:
        import urllib.error
        import urllib.request

        url = f"{self.endpoint}/{self.model}:generateContent"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")

        for attempt in range(self.pacer.max_attempts):
            self.pacer.wait_turn()
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = json.loads(response.read())
                return _first_text(payload)
            except urllib.error.HTTPError as exc:
                # 429 is the free tier working as designed; 5xx is transient.
                if exc.code not in (429, 500, 502, 503, 504):
                    raise
                if attempt == self.pacer.max_attempts - 1:
                    raise RateLimited(
                        f"{exc.code} after {self.pacer.max_attempts} attempts. "
                        "Check the per-project limits in AI Studio; the daily "
                        "cap does not reset until midnight Pacific."
                    ) from exc
                time.sleep(self.pacer.backoff_delay(attempt))
        raise RateLimited("retry budget exhausted")


@dataclass
class VertexProvider:
    """Gemini through Vertex (now "Gemini Enterprise Agent Platform").

    ADR-0010. Every role routes here: the AI Studio free tier is 20 requests
    per day per model, which cannot carry a 189-call measurement, and enabling
    billing on that key charges a card while Google Cloud credit sits unused —
    Gemini API is explicitly excluded from the Free Trial credit.

    **Location is `global`, not a region.** `gemini-3.6-flash` returns 404 in
    us-central1 and asia-south1; only the global endpoint serves it. Pinning a
    regional endpoint would fail outright, which is the good case — the bad
    case would have been a region silently serving a different model version.

    No sampling parameters, for the reason in ADR-0006.
    """

    model: str
    credentials_path: str
    project: str = ""
    location: str = "global"
    pacer: Pacer = field(default_factory=Pacer)
    name: str = "vertex"
    _token: str = field(default="", init=False, repr=False)
    _token_expiry: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.project:
            with open(self.credentials_path) as handle:
                self.project = json.load(handle)["project_id"]

    def _access_token(self) -> str:
        """Mint an OAuth2 token from the service account.

        Uses google-auth only for the RSA signing, which stdlib cannot do, and
        plain urllib for the exchange — so the dependency stays at one package
        rather than dragging in a second HTTP stack.
        """
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        import urllib.parse
        import urllib.request

        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        assertion = creds._make_authorization_grant_assertion()
        body = urllib.parse.urlencode(
            {
                "assertion": assertion,
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            }
        ).encode()
        request = urllib.request.Request(
            creds._token_uri,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    @property
    def endpoint(self) -> str:
        host = (
            "aiplatform.googleapis.com"
            if self.location == "global"
            else f"{self.location}-aiplatform.googleapis.com"
        )
        return (
            f"https://{host}/v1/projects/{self.project}"
            f"/locations/{self.location}/publishers/google/models"
        )

    def generate(self, prompt: str) -> str:
        import urllib.error
        import urllib.request

        url = f"{self.endpoint}/{self.model}:generateContent"
        body = json.dumps(
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        ).encode("utf-8")

        for attempt in range(self.pacer.max_attempts):
            self.pacer.wait_turn()
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._access_token()}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return _first_text(json.loads(response.read()))
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(
                        f"Vertex {exc.code}: {exc.read().decode()[:300]}"
                    ) from exc
                if attempt == self.pacer.max_attempts - 1:
                    raise RateLimited(
                        f"{exc.code} after {self.pacer.max_attempts} attempts"
                    ) from exc
                time.sleep(self.pacer.backoff_delay(attempt))
        raise RateLimited("retry budget exhausted")


def _first_text(payload: dict) -> str:
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"unexpected response shape: {payload}") from exc


@dataclass
class ResponseCache:
    """Keyed on (prompt_fingerprint, question_id, run_index).

    The fingerprint covers the template and every injected context file, so
    editing `business_context.md` invalidates the whole cache — which is
    correct, because the model would now be sent something different. This is
    the same hash ADR-0008 requires in the results file, so a cached run and
    its published score cannot drift apart.

    run_index is part of the key because cross-run variance (ADR-0001,
    threshold 3) needs three genuinely separate responses. Collapsing them
    would report perfect stability by construction.
    """

    root: Path = CACHE_DIR
    enabled: bool = True
    hits: int = 0
    misses: int = 0

    def _path(self, fingerprint: str, question_id: str, run_index: int) -> Path:
        return self.root / fingerprint / f"{question_id}.{run_index}.json"

    def get(self, fingerprint: str, question_id: str, run_index: int) -> str | None:
        if not self.enabled:
            return None
        path = self._path(fingerprint, question_id, run_index)
        if not path.exists():
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def put(
        self, fingerprint: str, question_id: str, run_index: int, response: str
    ) -> None:
        if not self.enabled:
            return
        path = self._path(fingerprint, question_id, run_index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "question_id": question_id,
                    "run_index": run_index,
                    "prompt_fingerprint": fingerprint,
                    "response": response,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def resolve_provider(role: str = "PLAN") -> Provider:
    """Build the provider for a model role from the environment.

    Model selection goes through role config and is never hardcoded at a call
    site (CONVENTIONS → API and agent).
    """
    model = env.text(f"MODEL_{role}")
    if not model:
        raise RuntimeError(
            f"MODEL_{role} is not set. Pin an exact model string — never a "
            "floating alias — so a result file describes a specific model."
        )
    rpm = env.integer("VERTEX_RPM", env.integer("GEMINI_RPM", 10))

    # Vertex first (ADR-0010). AI Studio is the documented fallback and is
    # capped at 20 requests per day per model, which no measurement survives.
    credentials = env.text("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials and Path(credentials).exists():
        return VertexProvider(
            model=model,
            credentials_path=credentials,
            location=env.text("VERTEX_LOCATION", "global"),
            pacer=Pacer(rpm=rpm),
        )

    api_key = env.text("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No credential. Set GOOGLE_APPLICATION_CREDENTIALS to the service "
            "account JSON (preferred, ADR-0010), or GEMINI_API_KEY to fall "
            "back to AI Studio at 20 requests/day."
        )
    return GeminiProvider(model=model, api_key=api_key, pacer=Pacer(rpm=rpm))


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
