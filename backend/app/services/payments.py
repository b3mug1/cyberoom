"""Provider-neutral payment checkout and refund boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import NoReturn, Protocol
import uuid
from urllib.parse import urljoin

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Booking, Club, Computer, Membership, MembershipPlan, Payment, User
from app.services.audit import record_audit
from app.services.errors import ServiceError


@dataclass(frozen=True)
class CheckoutSession:
    provider_reference: str
    checkout_url: str


@dataclass(frozen=True)
class RefundResult:
    provider_reference: str
    status: str


class PaymentAdapter(Protocol):
    """Implement this contract to connect any checkout and refund provider."""

    name: str
    configured: bool

    async def create_checkout(
        self, payment_id: uuid.UUID, amount: Decimal, currency: str, idempotency_key: str,
        success_url: str, cancel_url: str,
    ) -> CheckoutSession: ...
    async def get_status(self, provider_reference: str) -> str:
        """Return PENDING, PAID, FAILED, REFUND_PENDING, or REFUNDED."""
        ...
    async def refund(self, provider_reference: str, amount: Decimal, idempotency_key: str) -> RefundResult: ...
    async def cancel_checkout(self, provider_reference: str, idempotency_key: str) -> None: ...


class UnconfiguredPaymentAdapter:
    name = "unconfigured"
    configured = False

    def _unavailable(self) -> NoReturn:
        raise ServiceError("PAYMENT_PROVIDER_NOT_CONFIGURED", "Online payments are not configured for this service yet.", 503)

    async def create_checkout(
        self, payment_id: uuid.UUID, amount: Decimal, currency: str, idempotency_key: str,
        success_url: str, cancel_url: str,
    ) -> CheckoutSession:
        self._unavailable()

    async def get_status(self, provider_reference: str) -> str:
        self._unavailable()

    async def refund(self, provider_reference: str, amount: Decimal, idempotency_key: str) -> RefundResult:
        self._unavailable()

    async def cancel_checkout(self, provider_reference: str, idempotency_key: str) -> None:
        self._unavailable()


# Replace this adapter with an implementation of PaymentAdapter when a provider is selected.
payment_adapter: PaymentAdapter = UnconfiguredPaymentAdapter()


def _require_adapter() -> PaymentAdapter:
    if not payment_adapter.configured:
        raise ServiceError("PAYMENT_PROVIDER_NOT_CONFIGURED", "Online payments are not configured for this service yet.", 503)
    return payment_adapter


async def _payment_club_id(session: AsyncSession, payment: Payment) -> uuid.UUID | None:
    if payment.membership_plan_id is not None:
        return await session.scalar(select(MembershipPlan.club_id).where(MembershipPlan.id == payment.membership_plan_id))
    if payment.booking_id is not None:
        return await session.scalar(
            select(Computer.club_id).join(Booking, Booking.computer_id == Computer.id).where(Booking.id == payment.booking_id)
        )
    return None


async def _finish_checkout(session: AsyncSession, payment: Payment) -> Payment:
    adapter = _require_adapter()
    if payment.checkout_url and payment.status == "CHECKOUT_CREATED":
        return payment
    return_url = urljoin(get_settings().frontend_base_url.rstrip("/") + "/", f"payments/{payment.id}")
    checkout = await adapter.create_checkout(
        payment.id, payment.amount, payment.currency, payment.idempotency_key,
        success_url=return_url, cancel_url=return_url,
    )
    payment.provider = adapter.name
    payment.provider_reference = checkout.provider_reference
    payment.checkout_url = checkout.checkout_url
    payment.status = "CHECKOUT_CREATED"
    record_audit(
        session, actor_id=payment.user_id, action="payment.checkout_created", entity_type="payment", entity_id=payment.id,
        club_id=await _payment_club_id(session, payment), details={"amount": str(payment.amount), "currency": payment.currency},
    )
    await session.commit()
    await session.refresh(payment)
    return payment


async def start_booking_checkout(session: AsyncSession, user: User, booking_id: uuid.UUID) -> Payment:
    adapter = _require_adapter()
    booking = await session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None or booking.user_id != user.id:
        raise ServiceError("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.status not in ("PENDING", "CONFIRMED") or booking.start_time <= datetime.now(timezone.utc):
        raise ServiceError("BOOKING_NOT_PAYABLE", "Only an upcoming booking can be paid online.", 409)
    if booking.total_price <= 0:
        raise ServiceError("PAYMENT_NOT_REQUIRED", "No payment is due for this booking.", 409)
    payment = await session.scalar(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
    if payment is None:
        payment = Payment(user_id=user.id, booking_id=booking.id, amount=booking.total_price)
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
    elif payment.status == "PAID":
        raise ServiceError("PAYMENT_ALREADY_PAID", "This booking has already been paid.", 409)
    elif payment.status == "FAILED":
        payment.status = "PENDING"
        payment.provider_reference = None
        payment.checkout_url = None
        payment.idempotency_key = uuid.uuid4().hex
        await session.commit()
    elif payment.status in ("REFUND_PENDING", "REFUNDED"):
        raise ServiceError("PAYMENT_NOT_RETRYABLE", "This payment cannot be restarted.", 409)
    return await _finish_checkout(session, payment)


async def start_membership_checkout(session: AsyncSession, user: User, plan_id: uuid.UUID) -> Payment:
    adapter = _require_adapter()
    plan = await session.scalar(
        select(MembershipPlan).join(Club).where(
            MembershipPlan.id == plan_id, Club.is_active.is_(True),
        ).with_for_update(of=MembershipPlan)
    )
    if plan is None or not plan.is_active:
        raise ServiceError("MEMBERSHIP_PLAN_NOT_FOUND", "This membership plan is not available.", 404)
    existing = await session.scalar(select(Payment).where(
        Payment.user_id == user.id,
        Payment.membership_plan_id == plan.id,
        Payment.status.in_(("PENDING", "CHECKOUT_CREATED")),
    ).order_by(Payment.created_at.desc()).with_for_update())
    if existing is not None:
        return await _finish_checkout(session, existing)
    payment = Payment(user_id=user.id, membership_plan_id=plan.id, amount=plan.price)
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return await _finish_checkout(session, payment)


async def _activate_membership(session: AsyncSession, payment: Payment) -> None:
    if payment.membership_plan_id is None:
        return
    exists = await session.scalar(select(Membership.id).where(Membership.payment_id == payment.id))
    if exists is not None:
        return
    plan = await session.scalar(select(MembershipPlan).where(MembershipPlan.id == payment.membership_plan_id))
    if plan is None:
        raise ServiceError("MEMBERSHIP_PLAN_NOT_FOUND", "The purchased membership plan no longer exists.", 409)
    now = datetime.now(timezone.utc)
    minutes = plan.hours * 60
    session.add(Membership(
        user_id=payment.user_id,
        club_id=plan.club_id,
        plan_id=plan.id,
        payment_id=payment.id,
        total_minutes=minutes,
        remaining_minutes=minutes,
        starts_at=now,
        expires_at=now + timedelta(days=plan.validity_days),
    ))


async def get_user_payment(session: AsyncSession, user: User, payment_id: uuid.UUID) -> Payment:
    payment = await session.scalar(select(Payment).where(Payment.id == payment_id, Payment.user_id == user.id).with_for_update())
    if payment is None:
        raise ServiceError("PAYMENT_NOT_FOUND", "Payment not found.", 404)
    if payment.status in ("CHECKOUT_CREATED", "REFUND_PENDING") and payment.provider_reference:
        provider_state = await _require_adapter().get_status(payment.provider_reference)
        if payment.status == "CHECKOUT_CREATED" and provider_state in ("PAID", "FAILED"):
            payment.status = provider_state
            if provider_state == "PAID":
                await _activate_membership(session, payment)
            record_audit(
                session, actor_id=user.id, action="payment.status_changed", entity_type="payment", entity_id=payment.id,
                club_id=await _payment_club_id(session, payment), details={"status": provider_state},
            )
            await session.commit()
            await session.refresh(payment)
        elif payment.status == "REFUND_PENDING" and provider_state == "REFUNDED":
            payment.status = "REFUNDED"
            record_audit(
                session, actor_id=user.id, action="payment.refunded", entity_type="payment", entity_id=payment.id,
                club_id=await _payment_club_id(session, payment), details={"amount": str(payment.refund_amount)},
            )
            await session.commit()
            await session.refresh(payment)
    return payment


async def handle_booking_cancellation(
    session: AsyncSession, booking: Booking, *, refund_eligible: bool,
) -> None:
    payment = await session.scalar(select(Payment).where(Payment.booking_id == booking.id).with_for_update())
    if payment is None:
        return
    if payment.status == "CHECKOUT_CREATED" and payment.provider_reference:
        adapter = _require_adapter()
        provider_status = await adapter.get_status(payment.provider_reference)
        if provider_status == "PAID":
            payment.status = "PAID"
        elif provider_status == "FAILED":
            payment.status = "FAILED"
        elif provider_status == "PENDING":
            await adapter.cancel_checkout(payment.provider_reference, f"cancel-{payment.id}")
            payment.status = "FAILED"
        else:
            raise ServiceError("INVALID_PAYMENT_STATUS", "The payment adapter returned an invalid payment status.", 502)
    elif payment.status == "PENDING":
        payment.status = "FAILED"
    elif payment.status == "PAID" and refund_eligible:
        adapter = _require_adapter()
        if not payment.provider_reference:
            raise ServiceError("PAYMENT_REFERENCE_MISSING", "The payment provider reference is missing.", 409)
        result = await adapter.refund(payment.provider_reference, payment.amount, f"refund-{payment.id}")
        if result.status not in ("REFUND_PENDING", "REFUNDED"):
            raise ServiceError("INVALID_REFUND_STATUS", "The payment adapter returned an invalid refund status.", 502)
        payment.status = result.status
        payment.refund_amount = payment.amount
        payment.refund_reference = result.provider_reference
        record_audit(
            session, actor_id=booking.user_id, action="payment.refund_requested", entity_type="payment", entity_id=payment.id,
            club_id=await _payment_club_id(session, payment), details={"amount": str(payment.refund_amount), "status": payment.status},
        )

