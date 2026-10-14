# Architecture

The project is a modular monolith.

Cloud Core is the source of truth.

WordPress is an adapter.

WooCommerce is an integration layer.

Backend:
Python + FastAPI

Database:
PostgreSQL

Vector:
pgvector

Queue:
Redis + Celery

Primary API:
REST

Future AI interface:
MCP / compatible agent interfaces

The system is not a collection of independently deployed phases.

Each phase extends the same codebase.