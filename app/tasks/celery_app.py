import logging
from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "reseller",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "sync-amazon-products": {
            "task": "tasks.sync_amazon_products",
            "schedule": 43200,  # every 12 hours
        },
        "sync-ebay-listings": {
            "task": "tasks.sync_ebay_listings",
            "schedule": 3600,  # every 1 hour
        },
        "sync-ebay-orders": {
            "task": "tasks.sync_ebay_orders",
            "schedule": 1800,  # every 30 minutes
        },
        "refresh-amazon-prices": {
            "task": "tasks.refresh_amazon_prices",
            "schedule": settings.PRICE_SYNC_INTERVAL,
        },
        "sync-amazon-stock": {
            "task": "tasks.sync_amazon_stock",
            "schedule": settings.STOCK_SYNC_INTERVAL,
        },
        "sync-amazon-prices": {
            "task": "tasks.sync_amazon_prices",
            "schedule": settings.PRICE_SYNC_INTERVAL,
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])