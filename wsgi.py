"""WSGI entrypoint for production servers (gunicorn/uwsgi).

Example:
    gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:8000 wsgi:app

Use a SINGLE worker so the optional in-process refresh scheduler runs once.
For horizontal scaling, disable the in-process scheduler (GSID_INGEST_EVERY_HOURS=0)
and drive ingestion from an external cron / one-off job calling `python run.py --ingest`.
"""

from gsid.app import create_app

app = create_app()
