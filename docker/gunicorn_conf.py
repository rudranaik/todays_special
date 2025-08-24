import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT','8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", str(multiprocessing.cpu_count()))) or 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("TIMEOUT", "60"))
keepalive = 5
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
