import pytest
from pydantic import ValidationError

from app.schemas import ClubCreate, ClubUpdate


def test_club_accepts_iana_timezone() -> None:
    club = ClubCreate(name="Club", city="Astana", address="Test street", timezone="Asia/Almaty")
    assert club.timezone == "Asia/Almaty"


def test_club_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="valid IANA time zone"):
        ClubCreate(name="Club", city="Astana", address="Test street", timezone="Asia/Unknown")


def test_club_update_rejects_null_timezone() -> None:
    with pytest.raises(ValidationError, match="cannot be null"):
        ClubUpdate(timezone=None)
