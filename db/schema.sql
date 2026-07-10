-- Project 8: Text-to-SQL with Guardrails
-- Domain: SaaS subscriptions business
-- customers -> subscriptions (1:many, plan changes over time)
-- customers -> orders -> products (add-ons/services, category)
-- orders/subscriptions -> payments (exactly one of order_id/subscription_id set)

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    state         TEXT NOT NULL,
    tier          TEXT NOT NULL CHECK (tier IN ('basic', 'pro', 'enterprise')),
    signup_date   DATE NOT NULL
);

CREATE TABLE subscriptions (
    subscription_id      INTEGER PRIMARY KEY,
    customer_id          INTEGER NOT NULL REFERENCES customers(customer_id),
    plan_name            TEXT NOT NULL,
    subscription_start_date DATE NOT NULL,
    end_date             DATE,                  -- NULL means still active
    status               TEXT NOT NULL CHECK (status IN ('active', 'cancelled', 'expired'))
);

CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL CHECK (category IN ('Add-on', 'Service', 'Hardware')),
    price         REAL NOT NULL
);

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    order_date    DATE NOT NULL,
    amount        REAL NOT NULL,        -- actual charged amount (may differ from product.price via discount)
    status        TEXT NOT NULL CHECK (status IN ('completed', 'pending', 'refunded'))
);

CREATE TABLE payments (
    payment_id      INTEGER PRIMARY KEY,
    order_id        INTEGER REFERENCES orders(order_id),
    subscription_id INTEGER REFERENCES subscriptions(subscription_id),
    payment_date    DATE NOT NULL,
    amount          REAL NOT NULL,
    method          TEXT NOT NULL CHECK (method IN ('credit_card', 'paypal', 'bank_transfer')),
    status          TEXT NOT NULL CHECK (status IN ('succeeded', 'failed', 'refunded')),
    CHECK (
        (order_id IS NOT NULL AND subscription_id IS NULL) OR
        (order_id IS NULL AND subscription_id IS NOT NULL)
    )
);

CREATE INDEX idx_subscriptions_customer ON subscriptions(customer_id);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_product ON orders(product_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_payments_subscription ON payments(subscription_id);
