from backend.app.db.session import SessionLocal


def get_db():
    """Yield a SQLAlchemy Session that is guaranteed to be cleaned up.

    The previous implementation closed the session in ``finally`` but did
    not roll back any in-flight transaction.  When a handler raised after
    issuing SQL but before committing, the underlying connection went
    back to the pool in the ``idle in transaction`` state.  Under load
    that caused Postgres to refuse new connections ("too many clients
    already") and the pool to leak progressively.  Rolling back
    unconditionally before close fixes both.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            if db.in_transaction():
                db.rollback()
        except Exception:
            pass
        db.close()
