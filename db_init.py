"""
db_init.py
----------
Seeds the SQLite database with demo user profiles and store inventory.
Safe to re-run — skips rows that already exist.

Run once before starting the API:
  python db_init.py
"""

from database import SneakerInventory, User, WardrobeItem, get_session, init_db

SEED_USERS = [
    {
        "username": "john",
        "budget":   300.0,
        "wardrobe": [
            "Nike Air Force 1 Low White",
            "Jordan 1 Retro High OG Bred",
            "Nike Dunk Low Retro White Black",
        ],
    },
    {
        "username": "alice",
        "budget":   500.0,
        "wardrobe": [
            "New Balance 550 White Green",
            "Adidas Yeezy Boost 350 V2 Zebra",
            "Jordan 4 Retro Military Black",
            "Nike Air Max 90 White",
        ],
    },
    {
        "username": "demo",
        "budget":   400.0,
        "wardrobe": [],
    },
]


def seed_users():
    """
    seed_users
    ----------
    Inserts demo user profiles and their wardrobes. Skips existing users.
    """
    with get_session() as db:
        for profile in SEED_USERS:
            existing = db.query(User).filter_by(username=profile["username"]).first()
            if existing:
                print(f"  skip  user '{profile['username']}' (already exists)")
                continue

            user = User(username=profile["username"], budget=profile["budget"])
            db.add(user)
            db.flush()

            for sneaker_name in profile["wardrobe"]:
                db.add(WardrobeItem(user_id=user.id, sneaker_name=sneaker_name))

            print(f"  seeded user '{profile['username']}'  "
                  f"(budget=${profile['budget']}, "
                  f"{len(profile['wardrobe'])} wardrobe items)")


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
