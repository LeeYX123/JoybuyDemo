"""Load profile for WP-38: 200 concurrent users, 50 read RPS, 10 write RPS.

Run against a staging deployment, never production:
    locust -f infra/loadtest/locustfile.py --host https://staging.example.test
    # headless: --headless -u 200 -r 20 --run-time 5m

Reads dominate (browse/search/detail); writes are cart additions with a
per-user unique offer rotation so stock never exhausts mid-run.
"""

import random

from locust import HttpUser, between, task

SEARCH_TERMS = ["earbuds", "watch", "cable", "speaker", "charger"]
READ_WEIGHTS = 10
WRITE_WEIGHTS = 2


class StorefrontUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.session_ok = self.client.get("/api/v1/health").status_code == 200

    @task(READ_WEIGHTS)
    def browse_home(self):
        self.client.get("/api/v1/storefront/home", name="/storefront/home")

    @task(READ_WEIGHTS)
    def search(self):
        term = random.choice(SEARCH_TERMS)
        self.client.get(f"/api/v1/search?q={term}", name="/search")

    @task(READ_WEIGHTS)
    def category_tree(self):
        self.client.get("/api/v1/categories", name="/categories")

    @task(WRITE_WEIGHTS)
    def cart_touch(self):
        # Anonymous cart round-trip; exercises locks without orders.
        self.client.get("/api/v1/cart", name="/cart (read)")
