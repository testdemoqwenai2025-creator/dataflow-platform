"""
Seed script to populate DuckDB with sample datasets for development.
Usage: python scripts/seed_db.py
"""

import duckdb
import os
import random
import numpy as np
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "analytics.duckdb")

def create_sales_data(conn):
    """Create a realistic sales dataset with 10,000 rows."""
    conn.execute("DROP TABLE IF EXISTS sales_data")
    conn.execute("""
        CREATE TABLE sales_data (
            id INTEGER PRIMARY KEY,
            date DATE,
            region VARCHAR,
            product VARCHAR,
            category VARCHAR,
            quantity INTEGER,
            unit_price DOUBLE,
            revenue DOUBLE,
            cost DOUBLE,
            customer_id INTEGER
        )
    """)

    regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    categories = {
        "Electronics": ["Laptop", "Phone", "Tablet", "Monitor", "Headphones"],
        "Clothing": ["Jacket", "Shoes", "Shirt", "Pants", "Hat"],
        "Food & Beverage": ["Coffee", "Tea", "Juice", "Snacks", "Water"],
        "Home & Garden": ["Furniture", "Lamp", "Plant", "Tool", "Decor"],
    }

    rows = []
    base_date = datetime(2024, 1, 1)
    for i in range(1, 10001):
        category = random.choice(list(categories.keys()))
        product = random.choice(categories[category])
        region = random.choice(regions)
        date = base_date + timedelta(days=random.randint(0, 729))
        quantity = random.randint(1, 50)
        unit_price = round(random.uniform(10, 500), 2)
        revenue = round(quantity * unit_price, 2)
        cost = round(revenue * random.uniform(0.4, 0.8), 2)
        customer_id = random.randint(1, 500)
        rows.append((i, date, region, product, category, quantity, unit_price, revenue, cost, customer_id))

    conn.executemany(
        "INSERT INTO sales_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows
    )
    print(f"  Created sales_data: {len(rows)} rows")


def create_user_activity(conn):
    """Create user activity log with 50,000 rows."""
    conn.execute("DROP TABLE IF EXISTS user_activity")
    conn.execute("""
        CREATE TABLE user_activity (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action VARCHAR,
            page VARCHAR,
            duration_seconds INTEGER,
            timestamp TIMESTAMP
        )
    """)

    actions = ["page_view", "query_run", "dataset_upload", "chart_create", "export", "login", "logout"]
    pages = ["/dashboard", "/analytics", "/settings", "/data", "/analytics/query"]
    base = datetime(2024, 6, 1)

    rows = []
    for i in range(1, 50001):
        user_id = random.randint(1, 200)
        action = random.choice(actions)
        page = random.choice(pages)
        duration = random.randint(5, 600)
        ts = base + timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        rows.append((i, user_id, action, page, duration, ts))

    conn.executemany(
        "INSERT INTO user_activity VALUES (?, ?, ?, ?, ?, ?)",
        rows
    )
    print(f"  Created user_activity: {len(rows)} rows")


def create_products(conn):
    """Create product catalog."""
    conn.execute("DROP TABLE IF EXISTS products")
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            price DOUBLE,
            stock INTEGER,
            rating DOUBLE,
            launch_date DATE
        )
    """)

    products_data = [
        (1, "Pro Laptop 16\"", "Electronics", 2499.99, 150, 4.7, "2024-01-15"),
        (2, "Smartphone X", "Electronics", 999.99, 500, 4.5, "2024-03-01"),
        (3, "Wireless Earbuds", "Electronics", 149.99, 1000, 4.3, "2024-02-20"),
        (4, "4K Monitor", "Electronics", 599.99, 200, 4.6, "2024-04-10"),
        (5, "Mechanical Keyboard", "Electronics", 179.99, 350, 4.8, "2024-01-05"),
        (6, "Winter Jacket", "Clothing", 199.99, 300, 4.4, "2024-09-01"),
        (7, "Running Shoes", "Clothing", 129.99, 450, 4.2, "2024-05-15"),
        (8, "Organic Coffee", "Food & Beverage", 24.99, 2000, 4.9, "2024-01-01"),
        (9, "Desk Lamp", "Home & Garden", 79.99, 600, 4.1, "2024-06-01"),
        (10, "Indoor Plant Set", "Home & Garden", 49.99, 400, 4.6, "2024-03-15"),
    ]

    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", products_data)
    print(f"  Created products: {len(products_data)} rows")


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = duckdb.connect(DB_PATH)

    print("🌱 Seeding DuckDB with sample data...")
    create_sales_data(conn)
    create_user_activity(conn)
    create_products(conn)

    # Show summary
    print("\n📊 Database Summary:")
    tables = conn.execute("SHOW TABLES").fetchall()
    for (table,) in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")

    conn.close()
    print(f"\n✅ Database saved to: {DB_PATH}")


if __name__ == "__main__":
    main()
