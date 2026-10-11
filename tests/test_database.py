from sqlalchemy import text

from app.db.session import get_session, ping_database


def test_database_answers() -> None:
    ping_database()

    session = next(get_session())
    try:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        session.close()
