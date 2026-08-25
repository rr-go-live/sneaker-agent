"""
database.py
-----------
SQLAlchemy + SQLite data layer for user profiles, wardrobes, and inventory.

Tables:
  users             — one row per user (username, login, admin flag)
  wardrobe_items    — one row per sneaker per user (many-to-one → users)
  sneaker_inventory — one row per sneaker; quantity starts at 1 and decrements
                      when a sneaker is added to a wardrobe, making stock a
                      live transactional concept. There is no price ceiling —
                      any sneaker can be added regardless of cost.

Using SQLite with check_same_thread=False so the sync agents running inside
asyncio.to_thread can share the same engine without connection errors.

Usage:
  from database import get_session, User, WardrobeItem, SneakerInventory, init_db
  init_db()
  with get_session() as db:
      user = get_or_create_user(db, "john")
"""

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from auth import verify_password

DATABASE_URL = "sqlite:///./sneaker_agent.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    User
    ----
    One row per registered user.

    Fields:
        id            (int):   auto-increment primary key
        username      (str):   unique display name used as the lookup key
        password_hash (str):   PBKDF2 hash from auth.hash_password(); None
                                for rows created before login existed
        is_admin      (bool):  grants access to the custom eval scenario runner
        created_at    (dt):    row creation timestamp
        wardrobe      (list):  related WardrobeItem rows
    """
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=True)
    is_admin      = Column(Boolean, default=False, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow)

    wardrobe = relationship(
        "WardrobeItem",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="WardrobeItem.added_at",
    )


class WardrobeItem(Base):
    """
    WardrobeItem
    ------------
    One row per sneaker in a user's collection.

    Fields:
        id           (int): auto-increment primary key
        user_id      (int): FK → users.id
        sneaker_name (str): exact name matching SNEAKER_CATALOG keys
        added_at     (dt):  row creation timestamp
    """
    __tablename__ = "wardrobe_items"
    __table_args__ = (
        UniqueConstraint("user_id", "sneaker_name", name="uq_user_sneaker"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    sneaker_name = Column(String(256), nullable=False)
    added_at     = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="wardrobe")


# ─────────────────────────────────────────────────────────────────────────────
# Session factory
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def get_session():
    """
    get_session
    -----------
    Context manager that yields a SQLAlchemy Session and commits on success
    or rolls back on any exception.

    Usage:
        with get_session() as db:
            user = db.query(User).filter_by(username="john").first()
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """
    init_db
    -------
    Creates all tables if they do not already exist, then adds any columns
    that a newer version of the model expects but an existing database
    predates (SQLAlchemy's create_all only creates missing tables, it never
    alters an existing one). Safe to call on every app startup — a no-op
    once the schema is current.
    """
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns():
    """
    _add_missing_columns
    ---------------------
    Lightweight schema migration for SQLite: adds any column present on the
    User model but missing from an existing users table, so upgrading to a
    newer version of this app doesn't require deleting the database.

    Not a general migration framework — just enough to keep local dev
    databases in sync as the User model gains fields over time.
    """
    with engine.connect() as conn:
        existing_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")
        }

        if "password_hash" not in existing_columns:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(128)")
        if "is_admin" not in existing_columns:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
            )
        conn.commit()


def get_or_create_user(db: Session, username: str) -> User:
    """
    get_or_create_user
    ------------------
    Fetches an existing user by username or creates a new one if none exists.

    Args:
        db       (Session): active SQLAlchemy session
        username (str):     the username to look up or create

    Returns:
        User: the existing or newly created User row
    """
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        user = User(username=username)
        db.add(user)
        db.flush()
    return user


def get_user_wardrobe(username: str) -> list[str]:
    """
    get_user_wardrobe
    -----------------
    Returns the sneaker names in a user's wardrobe as a plain list of strings.
    Returns an empty list if the user does not exist.

    Args:
        username (str): the user to look up

    Returns:
        list[str]: sneaker names from the user's wardrobe
    """
    with get_session() as db:
        user = db.query(User).filter_by(username=username).first()
        if user is None:
            return []
        return [item.sneaker_name for item in user.wardrobe]


def verify_login(username: str, password: str) -> dict | None:
    """
    verify_login
    ------------
    Checks a username/password pair against the stored PBKDF2 hash.

    Args:
        username (str): the account to look up
        password (str): plaintext password attempt

    Returns:
        dict | None: {"username": str, "is_admin": bool} on success,
                      None if the user doesn't exist, has no password set
                      (pre-auth seed data), or the password is wrong
    """
    with get_session() as db:
        user = db.query(User).filter_by(username=username).first()
        if user is None or not user.password_hash:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return {"username": user.username, "is_admin": user.is_admin}


# ─────────────────────────────────────────────────────────────────────────────
# Store inventory
# ─────────────────────────────────────────────────────────────────────────────

class SneakerInventory(Base):
    """
    SneakerInventory
    ----------------
    One row per sneaker in the store. Each sneaker starts with quantity=1.
    Quantity is decremented on purchase and can never go below 0.

    Fields:
        sneaker_name (str): primary key; matches SNEAKER_CATALOG keys exactly
        quantity     (int): units available; 0 = out of stock
        updated_at   (dt):  last modification timestamp
    """
    __tablename__ = "sneaker_inventory"

    sneaker_name = Column(String(256), primary_key=True)
    quantity     = Column(Integer, default=1, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_sneaker_quantity(sneaker_name: str) -> int:
    """
    get_sneaker_quantity
    --------------------
    Returns the current stock quantity for a single sneaker. Returns 0 if
    the sneaker is not found in the inventory table.

    Args:
        sneaker_name (str): exact catalog name

    Returns:
        int: units in stock (0 = out of stock)
    """
    with get_session() as db:
        row = db.query(SneakerInventory).filter_by(sneaker_name=sneaker_name).first()
        return row.quantity if row else 0


def get_out_of_stock_names() -> set[str]:
    """
    get_out_of_stock_names
    ----------------------
    Returns the set of sneaker names with quantity = 0. Used by sneaker_agent
    to exclude sold-out items from its LLM selection pool.

    Returns:
        set[str]: sneaker names with no stock remaining
    """
    with get_session() as db:
        rows = (
            db.query(SneakerInventory.sneaker_name)
            .filter(SneakerInventory.quantity <= 0)
            .all()
        )
        return {row.sneaker_name for row in rows}


def purchase_sneaker(sneaker_name: str) -> bool:
    """
    purchase_sneaker
    ----------------
    Attempts to decrement the inventory for one sneaker by 1. Returns True
    on success, False if the sneaker is already out of stock or not found.

    SQLite serializes writes at the file level, so this is safe under the
    single-process usage pattern of a local dev server.

    Args:
        sneaker_name (str): exact catalog name to purchase

    Returns:
        bool: True if stock was decremented, False if out of stock
    """
    with get_session() as db:
        row = db.query(SneakerInventory).filter_by(sneaker_name=sneaker_name).first()
        if row is None or row.quantity <= 0:
            return False
        row.quantity -= 1
        row.updated_at = datetime.utcnow()
        return True
