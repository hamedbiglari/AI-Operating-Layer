#!/bin/bash
# Starts every service for the WordPress/WooCommerce ↔ Cloud Core E2E (processes do not persist between tool calls).
service postgresql start >/dev/null 2>&1
redis-server --daemonize yes --port 6379 >/dev/null 2>&1
service mariadb start >/dev/null 2>&1 || (mysqld_safe >/dev/null 2>&1 &)
export PATH=/home/claude/phase14/venv/bin:$PATH
export DATABASE_URL="postgresql+psycopg://aiol:aiol_dev_pw@localhost:5432/aiol_e2e" REDIS_URL="redis://localhost:6379/0" SECRET_KEY="dev-only-e2e-closure" APP_DEBUG=true
cd /home/claude/phase14/AI-Operating-Layer-Phase13-C-dashboard/cloud-core
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/e2e_uv.log 2>&1 &
nohup python -m celery -A app.workers.celery_app worker --pool=solo --loglevel=info > /tmp/e2e_cel.log 2>&1 &
cd /home/claude/wp
if [ -f wordpress/wp-config.php ]; then nohup php wp-cli.phar --allow-root --path=wordpress server --host=127.0.0.1 --port=8081 > /tmp/e2e_wp.log 2>&1 & fi
for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8000/ && break; sleep 1; done
for i in $(seq 1 20); do mysqladmin ping >/dev/null 2>&1 && break; sleep 1; done
if [ -f wordpress/wp-config.php ]; then for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8081/ && break; sleep 1; done; fi
