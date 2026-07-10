"""
Deterministic seed script for the Layer 0 SQLite database.
Run: python db/seed.py
Rebuilds db/guardrails.db from scratch every time (same seed -> same data),
so the eval set in eval/questions.json stays valid run after run.
"""
import random
import sqlite3
import datetime
import os

random.seed(42)

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")
DB_PATH = os.path.join(HERE, "guardrails.db")

# Fixed "today" for the whole eval set, so "last quarter" etc. stay stable
# regardless of when this script is actually run.
ANCHOR_DATE = datetime.date(2025, 7, 1)

FIRST_NAMES = [
    "Jordan", "Alex", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery",
    "Cameron", "Drew", "Elliot", "Harper", "Kendall", "Logan", "Parker",
    "Reese", "Sam", "Skyler", "Rowan", "Quinn",
]
LAST_NAMES = [
    "Blake", "Nguyen", "Patel", "Garcia", "Kim", "Chen", "Brooks", "Rivera",
    "Cohen", "Walsh", "Fischer", "Novak", "Reyes", "Diaz", "Okafor", "Singh",
]

# weighted so most customers are cheap-tier, a few enterprise
STATE_WEIGHTS = [
    ("CA", 20), ("NY", 14), ("TX", 13), ("FL", 10), ("WA", 8),
    ("IL", 7), ("MA", 6), ("CO", 6), ("GA", 6), ("NC", 5),
    ("OH", 4), ("AZ", 4), ("PA", 4), ("OR", 3),
]
TIER_WEIGHTS = [("basic", 60), ("pro", 30), ("enterprise", 10)]

PLAN_NAMES = {
    "basic": ["Basic Monthly"],
    "pro": ["Pro Monthly", "Pro Annual"],
    "enterprise": ["Enterprise Annual"],
}

PRODUCTS = [
    # (name, category, price)
    ("Extra Storage 100GB", "Add-on", 9.99),
    ("API Rate Limit Increase", "Add-on", 29.00),
    ("Priority Support", "Service", 49.00),
    ("Onboarding Package", "Service", 199.00),
    ("Custom Integration Setup", "Service", 499.00),
    ("Dedicated Account Manager", "Service", 999.00),
    ("Branded Hardware Token", "Hardware", 39.00),
    ("On-site Kiosk Device", "Hardware", 649.00),
]

PAYMENT_METHODS = ["credit_card", "paypal", "bank_transfer"]


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def random_date(start: datetime.date, end: datetime.date) -> datetime.date:
    span = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, max(span, 0)))


def build_schema(conn):
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())


def insert_fixed_customers(conn):
    """A handful of hand-crafted rows with known attributes, so lookup
    questions in eval/questions.json have a stable, guessable answer
    instead of depending on the random bulk generation below."""
    fixed = [
        # customer_id, name, email, state, tier, signup_date
        (1, "Jordan Blake", "jordan.blake@example.com", "CA", "enterprise", "2023-02-10"),
        (2, "Avery Nguyen", "avery.nguyen@example.com", "NY", "pro", "2023-05-22"),
        (3, "Riley Patel", "riley.patel@example.com", "TX", "basic", "2024-01-15"),
        (4, "Morgan Garcia", "morgan.garcia@example.com", "CA", "pro", "2024-06-30"),
        (5, "Casey Novak", "casey.novak@example.com", "FL", "basic", "2025-04-02"),
    ]
    conn.executemany(
        "INSERT INTO customers (customer_id, name, email, state, tier, signup_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        fixed,
    )
    return len(fixed)


def insert_random_customers(conn, start_id, count):
    used_emails = set()
    rows = []
    for i in range(count):
        cid = start_id + i
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
        used_emails.add(email)
        state = weighted_choice(STATE_WEIGHTS)
        tier = weighted_choice(TIER_WEIGHTS)
        signup = random_date(datetime.date(2023, 1, 1), datetime.date(2025, 6, 30))
        rows.append((cid, name, email, state, tier, signup.isoformat()))
    conn.executemany(
        "INSERT INTO customers (customer_id, name, email, state, tier, signup_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )


def insert_products(conn):
    rows = [(i + 1, *p) for i, p in enumerate(PRODUCTS)]
    conn.executemany(
        "INSERT INTO products (product_id, name, category, price) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def insert_subscriptions(conn, customers):
    """customers: list of (customer_id, tier, signup_date_str)"""
    rows = []
    sub_id = 1
    for cid, tier, signup_str in customers:
        signup = datetime.date.fromisoformat(signup_str)
        plan = random.choice(PLAN_NAMES[tier])
        start = signup  # first subscription starts at signup
        annual = "Annual" in plan
        duration_days = 365 if annual else random.randint(30, 300)
        natural_end = start + datetime.timedelta(days=duration_days)

        # Decide the fate of this (first) subscription.
        roll = random.random()
        if natural_end > ANCHOR_DATE:
            # still within its term as of the anchor date
            if roll < 0.85:
                status, end_date = "active", None
            else:
                # cancelled early, before its natural end
                cancel_date = random_date(start, min(natural_end, ANCHOR_DATE))
                status, end_date = "cancelled", cancel_date
        else:
            # term already elapsed by the anchor date
            if roll < 0.5:
                status, end_date = "expired", natural_end
            else:
                status, end_date = "cancelled", random_date(start, natural_end)

        rows.append((sub_id, cid, plan, start.isoformat(),
                     end_date.isoformat() if end_date else None, status))
        sub_id += 1

        # Some customers upgrade later -> a second subscription row.
        if tier in ("pro", "enterprise") and status != "active" and random.random() < 0.4:
            upgrade_start = end_date + datetime.timedelta(days=random.randint(1, 30)) if end_date else None
            if upgrade_start and upgrade_start <= ANCHOR_DATE:
                new_plan = random.choice(PLAN_NAMES["enterprise" if tier == "enterprise" else "pro"])
                rows.append((sub_id, cid, new_plan, upgrade_start.isoformat(), None, "active"))
                sub_id += 1

    conn.executemany(
        "INSERT INTO subscriptions "
        "(subscription_id, customer_id, plan_name, subscription_start_date, end_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    return rows


def insert_orders(conn, customers, product_ids_with_price):
    rows = []
    order_id = 1
    for cid, tier, signup_str in customers:
        signup = datetime.date.fromisoformat(signup_str)
        # not everyone buys add-ons; enterprise/pro customers buy more often
        base_rate = {"basic": 0.35, "pro": 0.55, "enterprise": 0.8}[tier]
        if random.random() > base_rate:
            continue
        n_orders = random.randint(1, 4)
        for _ in range(n_orders):
            product_id, price = random.choice(product_ids_with_price)
            order_date = random_date(signup, ANCHOR_DATE)
            discount = random.choice([1.0, 1.0, 1.0, 0.9, 0.85])  # occasional discount
            amount = round(price * discount, 2)
            status = weighted_choice([("completed", 85), ("pending", 8), ("refunded", 7)])
            rows.append((order_id, cid, product_id, order_date.isoformat(), amount, status))
            order_id += 1
    conn.executemany(
        "INSERT INTO orders (order_id, customer_id, product_id, order_date, amount, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    return rows


def insert_payments(conn, orders, subscriptions):
    rows = []
    payment_id = 1

    # Payments for orders (skip refunded orders' original charge being "clean")
    for order_id, _cid, _product_id, order_date_str, amount, status in orders:
        order_date = datetime.date.fromisoformat(order_date_str)
        if status == "refunded":
            # original charge succeeded, then a refunded payment row
            rows.append((payment_id, order_id, None, order_date.isoformat(),
                         amount, random.choice(PAYMENT_METHODS), "succeeded"))
            payment_id += 1
            refund_date = order_date + datetime.timedelta(days=random.randint(1, 14))
            if refund_date <= ANCHOR_DATE:
                rows.append((payment_id, order_id, None, refund_date.isoformat(),
                             amount, random.choice(PAYMENT_METHODS), "refunded"))
                payment_id += 1
        elif status == "pending":
            rows.append((payment_id, order_id, None, order_date.isoformat(),
                         amount, random.choice(PAYMENT_METHODS), "failed"))
            payment_id += 1
        else:  # completed
            if random.random() < 0.1:
                # a failed attempt before the successful one
                rows.append((payment_id, order_id, None, order_date.isoformat(),
                             amount, random.choice(PAYMENT_METHODS), "failed"))
                payment_id += 1
            rows.append((payment_id, order_id, None, order_date.isoformat(),
                         amount, random.choice(PAYMENT_METHODS), "succeeded"))
            payment_id += 1

    # Renewal payments for subscriptions (order_id NULL, subscription_id set)
    for sub_id, _cid, plan_name, start_str, end_str, status in subscriptions:
        start = datetime.date.fromisoformat(start_str)
        end = datetime.date.fromisoformat(end_str) if end_str else ANCHOR_DATE
        is_annual = "Annual" in plan_name
        price = {"Basic Monthly": 15.0, "Pro Monthly": 45.0, "Pro Annual": 450.0,
                 "Enterprise Annual": 2400.0}.get(plan_name, 45.0)
        cycle_days = 365 if is_annual else 30
        cursor_date = start
        while cursor_date <= min(end, ANCHOR_DATE):
            pay_status = "succeeded" if random.random() > 0.03 else "failed"
            rows.append((payment_id, None, sub_id, cursor_date.isoformat(),
                         price, random.choice(PAYMENT_METHODS), pay_status))
            payment_id += 1
            cursor_date += datetime.timedelta(days=cycle_days)

    conn.executemany(
        "INSERT INTO payments "
        "(payment_id, order_id, subscription_id, payment_date, amount, method, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return rows


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    build_schema(conn)

    n_fixed = insert_fixed_customers(conn)
    insert_random_customers(conn, start_id=n_fixed + 1, count=295)
    insert_products(conn)
    conn.commit()

    customers = conn.execute(
        "SELECT customer_id, tier, signup_date FROM customers ORDER BY customer_id"
    ).fetchall()
    product_ids_with_price = conn.execute(
        "SELECT product_id, price FROM products"
    ).fetchall()

    subscriptions = insert_subscriptions(conn, customers)
    conn.commit()

    orders = insert_orders(conn, customers, product_ids_with_price)
    conn.commit()

    insert_payments(conn, orders, subscriptions)
    conn.commit()

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("customers", "subscriptions", "products", "orders", "payments")
    }
    conn.close()

    print(f"Built {DB_PATH}")
    for table, n in counts.items():
        print(f"  {table:14s} {n} rows")


if __name__ == "__main__":
    main()
