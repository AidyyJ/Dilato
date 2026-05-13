# Import all task modules so Celery autodiscover finds them
from app.tasks.amazon_tasks import sync_amazon_products, refresh_amazon_prices  # noqa: F401
from app.tasks.ebay_tasks import sync_ebay_listings, publish_ebay_listing  # noqa: F401
from app.tasks.order_sync import sync_ebay_orders  # noqa: F401
from app.tasks.price_sync import sync_amazon_prices  # noqa: F401
from app.tasks.stock_sync import sync_amazon_stock  # noqa: F401
from app.tasks.sourcing_tasks import run_sourcing_scan  # noqa: F401
