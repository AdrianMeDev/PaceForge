"""What a user's AI calls cost, from the prices the user entered themselves.

Prices are optional and per model. Every function acts on the data of the user it is given and on
nothing else. Money is ``Decimal`` throughout, never ``float``.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from goals.services import time_zone_of

from .models import MAX_MODEL_PRICES, AIModelPrice, AIUsageRecord

MONTHS = 12
MILLION = Decimal(1_000_000)


class PriceLimitError(Exception):
    """The user already keeps ``MAX_MODEL_PRICES`` prices."""


@dataclass(frozen=True)
class MonthlyUsage:
    month: str  # "2026-11", the calendar month in the user's time zone
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    # The cost of the calls whose model has a price; ``None`` if no call of the month has one.
    cost: Decimal | None
    # The models used in the month without a price, sorted. The cost leaves their calls out.
    unpriced_models: list[str] = field(default_factory=list)


def _now() -> datetime:
    return timezone.now()


def cost_of(
    price: AIModelPrice,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
) -> Decimal:
    """The cost in USD of one call at ``price``. Unknown token counts count as zero.

    The cached tokens are part of the input: they are charged at the cached price (the input
    price if there is none) and the rest of the input at the input price.
    """
    total_input = input_tokens or 0
    cached = min(cache_read_tokens or 0, total_input)
    cached_price = (
        price.input_per_million if price.cached_per_million is None else price.cached_per_million
    )
    return (
        (total_input - cached) * price.input_per_million
        + cached * cached_price
        + (output_tokens or 0) * price.output_per_million
    ) / MILLION


def list_prices(user: User) -> list[AIModelPrice]:
    return list(AIModelPrice.objects.for_user(user).order_by("model"))


def save_price(
    user: User,
    model: str,
    input_per_million: Decimal,
    output_per_million: Decimal,
    cached_per_million: Decimal | None = None,
) -> AIModelPrice:
    """Create or replace the price of ``model`` for ``user``. The values are validated.

    Raises ``django.core.exceptions.ValidationError`` for a bad value and ``PriceLimitError`` if
    this would be one price too many.
    """
    with transaction.atomic():
        prices = AIModelPrice.objects.for_user(user)
        price = prices.filter(model=model).first() or AIModelPrice(owner=user, model=model)
        if price.pk is None and prices.count() >= MAX_MODEL_PRICES:
            raise PriceLimitError
        price.input_per_million = input_per_million
        price.output_per_million = output_per_million
        price.cached_per_million = cached_per_million
        price.full_clean(exclude=["owner"], validate_unique=False)
        price.save()
    return price


def delete_price(user: User, model: str) -> bool:
    """Remove the price of ``model``; False if the user had none."""
    deleted, _ = AIModelPrice.objects.for_user(user).filter(model=model).delete()
    return deleted > 0


def monthly_usage(user: User, months: int = MONTHS) -> list[MonthlyUsage]:
    """The user's calls per calendar month in their time zone, newest first.

    Covers the current and the ``months - 1`` months before it; months without calls are left
    out. Failed calls are included, as in the usage summary.
    """
    zone = time_zone_of(user)
    now = _now().astimezone(zone)
    index = now.year * 12 + now.month - 1 - (months - 1)
    first = datetime(index // 12, index % 12 + 1, 1, tzinfo=zone)
    prices = {p.model: p for p in AIModelPrice.objects.for_user(user)}

    class Bucket:
        def __init__(self) -> None:
            self.calls = self.input = self.output = self.read = self.write = 0
            self.cost: Decimal | None = None
            self.unpriced: set[str] = set()

    buckets: defaultdict[str, Bucket] = defaultdict(Bucket)
    records = (
        AIUsageRecord.objects.for_user(user)
        .filter(created_at__gte=first)
        .values_list(
            "created_at",
            "model",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )
    for created_at, model, input_tokens, output_tokens, read, write in records.iterator():
        local = created_at.astimezone(zone)
        bucket = buckets[f"{local.year:04d}-{local.month:02d}"]
        bucket.calls += 1
        bucket.input += input_tokens or 0
        bucket.output += output_tokens or 0
        bucket.read += read or 0
        bucket.write += write or 0
        price = prices.get(model)
        if price is None:
            bucket.unpriced.add(model)
        else:
            bucket.cost = (bucket.cost or Decimal(0)) + cost_of(
                price, input_tokens, output_tokens, read
            )
    return [
        MonthlyUsage(
            month=month,
            calls=b.calls,
            input_tokens=b.input,
            output_tokens=b.output,
            cache_read_tokens=b.read,
            cache_write_tokens=b.write,
            cost=b.cost,
            unpriced_models=sorted(b.unpriced),
        )
        for month, b in sorted(buckets.items(), reverse=True)
    ]
