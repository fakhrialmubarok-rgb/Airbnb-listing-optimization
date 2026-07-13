"""
Creem.io payment integration for ListingBoost.

Setup:
  1. Go to https://www.creem.io → Products → Create product
     Name: ListingBoost  Price: $197  Type: One-time
  2. Copy the product ID (looks like prod_xxxxxxxx)
  3. Set CREEM_PRODUCT_ID=prod_xxxxxxxx in .env

Usage:
  from creem_payment import create_checkout_link, poll_payment_status

  url = create_checkout_link(
      product_id="prod_xxx",
      customer_email="host@example.com",
      metadata={"listing_id": "20669368", "host_name": "Tanya"},
  )
  # Send this URL to the host; they pay → Creem fires a webhook

  # Or poll for payment status (simple approach, no webhook server needed):
  paid = poll_payment_status(order_id="ord_xxx")
"""

from __future__ import annotations
import os, time
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

_BASE    = "https://api.creem.io/v1"
_API_KEY = os.environ.get("CREEM_API_KEY", "")
_HEADERS = {
    "x-api-key":    _API_KEY,
    "Content-Type": "application/json",
}


# ── Checkout link ─────────────────────────────────────────────────────────────

def create_checkout_link(
    product_id: str,
    customer_email: str | None = None,
    metadata: dict | None = None,
    success_url: str = "https://scalr-us.com/thank-you",
    discount_code: str | None = None,
    request_id: str | None = None,
) -> str:
    """
    Create a Creem checkout link for the given product.

    Pricing pattern: product is set to $197 (anchor).
    Pass discount_code="FAST29" to pre-apply the $168-off code,
    bringing the checkout total to $29.

    Docs endpoint: POST /v1/checkout-links
    """
    payload: dict = {"product_id": product_id, "success_url": success_url}
    if customer_email:
        payload["customer_email"] = customer_email
    if metadata:
        payload["metadata"] = metadata
    if discount_code:
        payload["discount_code"] = discount_code
    if request_id:
        payload["request_id"] = request_id

    resp = requests.post(
        f"{_BASE}/checkout-links",
        headers=_HEADERS,
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    url = data.get("checkout_url") or data.get("url") or data.get("link")
    if not url:
        raise ValueError(f"No URL in Creem response: {data}")
    return url


# ── Payment status ─────────────────────────────────────────────────────────────

def get_order(order_id: str) -> dict:
    """Fetch a Creem order by ID."""
    resp = requests.get(
        f"{_BASE}/orders/{order_id}",
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def poll_payment_status(
    order_id: str,
    timeout_seconds: int = 3600,
    poll_interval: int = 60,
) -> bool:
    """
    Poll until an order is paid (status == "paid") or timeout.
    Returns True if paid, False if timed out.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            order = get_order(order_id)
            status = order.get("status", "").lower()
            if status in ("paid", "complete", "completed", "succeeded", "success"):
                return True
            if status in ("failed", "canceled", "cancelled", "refunded"):
                return False
        except requests.HTTPError as e:
            print(f"  [creem] poll error: {e}")
        time.sleep(poll_interval)
    return False


# ── Webhook verification (for future use) ─────────────────────────────────────

def verify_webhook(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """
    Verify a Creem webhook signature.
    Creem sends X-Creem-Signature header as HMAC-SHA256 of raw body.
    """
    import hashlib, hmac
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse, json
    parser = argparse.ArgumentParser(description="Creem.io payment tools")
    sub = parser.add_subparsers(dest="cmd")

    # create-link
    lp = sub.add_parser("create-link", help="Create a checkout link")
    lp.add_argument("--product-id", required=True)
    lp.add_argument("--email")
    lp.add_argument("--listing-id")
    lp.add_argument("--host-name")
    lp.add_argument("--success-url", default="https://scalr-us.com/thank-you")
    lp.add_argument("--discount-code", default=os.environ.get("CREEM_DISCOUNT_CODE", "FAST29"),
                    help="Pre-applied discount code (default: FAST29)")

    # check-order
    op = sub.add_parser("check-order", help="Check payment status of an order")
    op.add_argument("--order-id", required=True)

    # list-products
    sub.add_parser("list-products", help="List products (need product_id)")

    args = parser.parse_args()

    if args.cmd == "create-link":
        meta = {}
        if args.listing_id: meta["listing_id"] = args.listing_id
        if args.host_name:   meta["host_name"]  = args.host_name
        url = create_checkout_link(
            product_id=args.product_id,
            customer_email=args.email,
            metadata=meta or None,
            success_url=args.success_url,
            discount_code=args.discount_code or None,
        )
        print(f"\nCheckout URL:\n{url}\n")

    elif args.cmd == "check-order":
        order = get_order(args.order_id)
        print(json.dumps(order, indent=2))

    elif args.cmd == "list-products":
        pid = os.environ.get("CREEM_PRODUCT_ID")
        if not pid:
            print("Set CREEM_PRODUCT_ID in .env (get it from Creem dashboard)")
            return
        resp = requests.get(f"{_BASE}/products?product_id={pid}", headers=_HEADERS, timeout=10)
        print(json.dumps(resp.json(), indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
