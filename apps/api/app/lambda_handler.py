"""AWS Lambda entrypoint. Handler path: app.lambda_handler.handler

Wraps the existing FastAPI app with Mangum; this module changes nothing about local
development, which still runs the same app directly via
`uvicorn app.main:app --reload`.

Deliberately does not run database migrations here: migrations are applied out of band
before a deploy (e.g. `alembic upgrade head` from a CI step or operator machine), never
implicitly on a Lambda cold start.

The in-process scheduler (app/services/scheduler.py) is not started here or anywhere in
this module. It is controlled entirely by `ENABLE_SCHEDULER`, which production Lambda
configuration sets to false -- so no APScheduler background loop is ever created inside a
Lambda invocation.
"""
from mangum import Mangum

from app.main import app

handler = Mangum(app)
