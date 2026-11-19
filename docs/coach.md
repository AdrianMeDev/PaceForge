# AI coach

PaceForge lets each athlete connect their own AI provider (Anthropic or an OpenAI-compatible
endpoint), route different tasks to different models, and track monthly token usage and estimated
costs.

## Model-per-task routing

Each user has at most one `AIProviderConfiguration` (`backend/coach/models.py`) with a required
default `model` and three optional task-specific models:

| Field | Task (`AIUsageRecord.Purpose`) | Fallback when blank |
| --- | --- | --- |
| `season_model` | `season_plan` | `model` |
| `week_model` | `weekly_plan` | `model` |
| `chat_model` | `chat` | `model` |
| `model` | `check`, `week_review`, and default | — |

`AIProviderConfiguration.model_for(purpose)` selects the task model if non-empty and falls back to
`model`. All tasks share the same `provider`, `base_url` (for `openai_compatible`), and `api_key`.

- **Validation:** Every model name has at most `MODEL_MAX` (`100`) characters and must match
  `^[A-Za-z0-9][A-Za-z0-9._:/-]*\Z`.
- **Status reset:** Changing `provider`, `model`, `season_model`, `week_model`, `chat_model`,
  `base_url`, or `api_key` resets `status` to `untested` and clears `last_checked_at` and
  `last_success_at`. Saving the exact same values leaves the status unchanged.
- **History:** Each `AIUsageRecord` stores the `model` string used at the time of the call, so
  later configuration changes or removals do not alter historical records.

## Per-model pricing (`AIModelPrice`)

Model prices are optional and entered by each user in USD per million tokens; PaceForge ships no
built-in price list.

| Field | Type / constraints | Meaning |
| --- | --- | --- |
| `model` | `CharField(max_length=100)`, `MODEL_PATTERN`, unique per `(owner, model)` | Model name matching the provider's name |
| `input_per_million` | `Decimal(10, 4)`, `0` to `999999.9999` | Price per 1,000,000 non-cached input tokens |
| `output_per_million` | `Decimal(10, 4)`, `0` to `999999.9999` | Price per 1,000,000 output tokens |
| `cached_per_million` | `Decimal(10, 4)`, nullable, `0` to `999999.9999` | Price per 1,000,000 input tokens read from the prompt cache (`null` uses `input_per_million`) |

- **Per-user limit:** A user can keep at most `MAX_MODEL_PRICES` (`50`) prices. Attempting to add
  a 51st model raises `PriceLimitError` and returns a validation error on `model`.
- **Input format:** The API (`PriceField` in `backend/coach/serializers.py`) accepts a finite JSON
  number (not a string or boolean) from `0` to `999999.9999` with at most `4` decimal places, and
  serializes values as decimal strings.

## Monthly cost calculation

`monthly_usage` (`backend/coach/pricing.py`) aggregates `AIUsageRecord` rows over the current
calendar month and the `11` preceding calendar months (`MONTHS = 12`).

- **Time zone:** Calendar months (`YYYY-MM`) are determined in the user's profile time zone
  (`time_zone_of(user)`). Months with zero calls are omitted; results are ordered newest first.
- **Included calls:** All calls that reached the provider—including failed calls (`invalid_key`,
  `rate_limited`, `unavailable`, `unexpected`)—are counted, matching the 30-day usage summary.
- **Token and cache math (`cost_of`):** All calculations use `Decimal`, never `float`. Missing
  (`None`) token counts are treated as `0`. `cache_read_tokens` are part of `input_tokens` (not on
  top of them) and are clamped to `min(cache_read_tokens or 0, total_input)`:
  - Non-cached input (`total_input - cached`) is billed at `input_per_million`.
  - Cached reads (`cached`) are billed at `cached_per_million` if set, otherwise `input_per_million`.
  - Output (`output_tokens`) is billed at `output_per_million`.
  - `cache_write_tokens` are summed in usage totals and not billed separately in `cost_of`.
- **Partial pricing:** Each call is priced using the user's `AIModelPrice` for `record.model`.
  - If some models used in a month have prices and others do not, `cost` is the sum for the
    priced models (quantized to `4` decimal places in the API) and `unpriced_models` lists the
    remaining models sorted alphabetically. The UI displays `At least $…` with the unpriced list.
  - If no call in the month has a matching price, `cost` is `null` and the UI displays `No price set`.

## API endpoints

All endpoints require an authenticated session and operate exclusively on `request.user`:

- `GET /api/coach/provider/`: returns the provider setup (including `season_model`, `week_model`,
  `chat_model`), `allowed_base_urls`, and the 30-day `usage` summary.
- `PUT /api/coach/provider/`: creates or replaces the provider setup.
- `DELETE /api/coach/provider/`: deletes the provider setup and stored key (`204`).
- `POST /api/coach/provider/check/`: sends the fixed check prompt (`Reply with the single word: ok`,
  max 16 tokens) using `model`; rate-limited to `10` requests per minute per user (`CoachCheckThrottle`).
- `GET /api/coach/costs/`: returns `prices` (ordered by `model`) and `months` (up to `12` months,
  newest first).
- `PUT /api/coach/costs/prices/`: creates or replaces the `AIModelPrice` for `model` and returns
  the updated `costs` payload.
- `DELETE /api/coach/costs/prices/<int:price_id>/`: deletes one `AIModelPrice` (`204`, or `404` if
  not found for the requesting user).

## User isolation and privacy boundaries

- **Strict user scoping:** Every query on `AIProviderConfiguration`, `AIUsageRecord`, and
  `AIModelPrice` uses `.for_user(user)`. Endpoints take no user parameter, and one user can never
  read, modify, or delete another user's configuration, usage history, or prices.
- **Write-only API key:** `api_key` is stored encrypted (`EncryptedTextField`), never returned by
  any endpoint, never logged, and never included in error responses.
- **Metadata-only usage logs:** `AIUsageRecord` keeps only provider, model, purpose, outcome,
  token counts, and timestamp—never prompts, responses, or provider error text.
- **Per-user prompt caching:** Prompt caching uses the user's own API key and provider account;
  nothing is shared across users on the instance.
- **Endpoint allowlist:** OpenAI-compatible `base_url` values must match `AI_ALLOWED_BASE_URLS`,
  re-checked on every call, with HTTP redirects disabled.
