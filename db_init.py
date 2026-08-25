"""
db_init.py
----------
Seeds the SQLite database with demo user profiles and store inventory.
Safe to re-run — skips rows that already exist.

Run once before starting the API:
  python db_init.py

Demo logins (local dev only — change these before deploying anywhere real):
  john  / john
  alice / alice
  demo  / demo
  admin / admin   (is_admin=True — custom eval scenarios)
"""

from auth import hash_password
from database import SneakerInventory, User, WardrobeItem, get_session, init_db

SEED_USERS = [
    {
        "username": "john",
        "password": "john",
        "is_admin": False,
        "wardrobe": [
            "Nike Air Force 1 Low '07 White",
            "Jordan 1 Retro High OG Patent Bred",
            "Nike Dunk Low Retro White Black Panda (2021)",
        ],
    },
    {
        "username": "alice",
        "password": "alice",
        "is_admin": False,
        "wardrobe": [
            "New Balance 550 White Green",
            "adidas Yeezy Boost 350 V2 Zebra",
            "Jordan 4 Retro Military Black",
            "Nike Air Max 90 Recraft Triple White",
        ],
    },
    {
        "username": "demo",
        "password": "demo",
        "is_admin": False,
        "wardrobe": [],
    },
    {
        "username": "admin",
        "password": "admin",
        "is_admin": True,
        "wardrobe": [],
    },
]


# sneakerdata.json has been re-generated since these demo wardrobes were
# first seeded, and a few names drifted from what's actually in the catalog
# now (a stale name, or — for the Yeezy — just a capitalization mismatch).
# Applied every run so an already-seeded database gets corrected too, not
# just fresh installs; harmless no-op once a row is already fixed.
WARDROBE_NAME_FIXES = {
    "Nike Air Force 1 Low White":      "Nike Air Force 1 Low '07 White",
    "Jordan 1 Retro High OG Bred":     "Jordan 1 Retro High OG Patent Bred",
    "Nike Dunk Low Retro White Black": "Nike Dunk Low Retro White Black Panda (2021)",
    "Adidas Yeezy Boost 350 V2 Zebra": "adidas Yeezy Boost 350 V2 Zebra",
    "Nike Air Max 90 White":           "Nike Air Max 90 Recraft Triple White",
}


def fix_stale_wardrobe_names(db):
    """
    fix_stale_wardrobe_names
    --------------------------
    Renames any wardrobe row still holding a pre-drift sneaker name to its
    current catalog equivalent, so the Wardrobe tab can find a real catalog
    match instead of falling back to a bare stub card.

    Args:
        db (Session): active SQLAlchemy session

    Returns:
        None
    """
    fixed = 0
    for old_name, new_name in WARDROBE_NAME_FIXES.items():
        rows = db.query(WardrobeItem).filter_by(sneaker_name=old_name).all()
        for row in rows:
            row.sneaker_name = new_name
            fixed += 1

    if fixed:
        print(f"  corrected {fixed} stale wardrobe name(s) to match the current catalog")


def seed_users():
    """
    seed_users
    ----------
    Inserts demo user profiles and their wardrobes. For a user that already
    exists but predates login (no password_hash set), backfills the seed
    password and is_admin flag in place without touching their existing
    wardrobe — so upgrading to this feature doesn't require deleting the
    database. A user that already has a password is left untouched. Stale
    wardrobe names are corrected regardless (see fix_stale_wardrobe_names),
    since that's a data fix, not a schema one.
    """
    with get_session() as db:
        fix_stale_wardrobe_names(db)

        for profile in SEED_USERS:
            existing = db.query(User).filter_by(username=profile["username"]).first()

            if existing:
                if existing.password_hash:
                    print(f"  skip  user '{profile['username']}' (already exists)")
                    continue
                existing.password_hash = hash_password(profile["password"])
                existing.is_admin = profile["is_admin"]
                print(f"  updated user '{profile['username']}' (added login)")
                continue

            user = User(
                username=profile["username"],
                password_hash=hash_password(profile["password"]),
                is_admin=profile["is_admin"],
            )
            db.add(user)
            db.flush()

            for sneaker_name in profile["wardrobe"]:
                db.add(WardrobeItem(user_id=user.id, sneaker_name=sneaker_name))

            print(f"  seeded user '{profile['username']}'  "
                  f"({len(profile['wardrobe'])} wardrobe items)")


def seed_inventory():
    """
    seed_inventory
    --------------
    Inserts one inventory row per sneaker in the catalog, each starting with
    quantity=1. Skips the seed entirely if any inventory rows already exist
    so a re-run never doubles the stock.
    """
    from data.catalog import SNEAKER_CATALOG

    with get_session() as db:
        existing_count = db.query(SneakerInventory).count()
        if existing_count > 0:
            print(f"  skip  inventory ({existing_count:,} rows already seeded)")
            return

        rows = [
            SneakerInventory(sneaker_name=name, quantity=1)
            for name in SNEAKER_CATALOG
        ]
        db.bulk_save_objects(rows)
        print(f"  seeded inventory: {len(rows):,} sneakers × 1 unit each")


def seed():
    """
    seed
    ----
    Initialises DB tables, seeds users, and seeds store inventory.
    """
    init_db()
    seed_users()
    seed_inventory()
    print("\nDatabase ready: sneaker_agent.db")


if __name__ == "__main__":
    seed()
