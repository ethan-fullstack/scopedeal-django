FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .
RUN useradd --create-home app && chown -R app:app /app
USER app
RUN DJANGO_SETTINGS_MODULE=config.settings.base .venv/bin/python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["/app/.venv/bin/gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
