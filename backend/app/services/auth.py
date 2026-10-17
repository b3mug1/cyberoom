from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, hash_password, hash_refresh_token, verify_password
from app.models import RefreshSession, User
from app.schemas import TokenPair, UserCreate, UserLogin
from app.services.errors import ServiceError


async def register(session: AsyncSession, payload: UserCreate) -> tuple[User, TokenPair]:
    user = User(
        email=str(payload.email).lower(),
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    try:
        await session.flush()
        tokens = await issue_tokens(session, user)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ServiceError("ACCOUNT_EXISTS", "That email or username is already registered.", 409) from error
    await session.refresh(user)
    return user, tokens


async def login(session: AsyncSession, payload: UserLogin) -> tuple[User, TokenPair]:
    user = await session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise ServiceError("INVALID_CREDENTIALS", "Email or password is incorrect.", 401)
    tokens = await issue_tokens(session, user)
    await session.commit()
    return user, tokens


async def refresh(session: AsyncSession, token: str) -> TokenPair:
    token_session = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(token)).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if token_session is None or token_session.revoked_at is not None or token_session.expires_at <= now:
        raise ServiceError("INVALID_REFRESH_TOKEN", "The refresh token is invalid or expired.", 401)
    user = await session.get(User, token_session.user_id)
    if user is None or not user.is_active:
        raise ServiceError("INVALID_REFRESH_TOKEN", "The refresh token is invalid or expired.", 401)
    token_session.revoked_at = now
    tokens = await issue_tokens(session, user)
    await session.commit()
    return tokens


async def logout(session: AsyncSession, token: str) -> None:
    token_session = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(token)).with_for_update()
    )
    if token_session is not None and token_session.revoked_at is None:
        token_session.revoked_at = datetime.now(timezone.utc)
        await session.commit()


async def issue_tokens(session: AsyncSession, user: User) -> TokenPair:
    settings = get_settings()
    refresh_token = create_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    return TokenPair(access_token=create_access_token(user.id), refresh_token=refresh_token)