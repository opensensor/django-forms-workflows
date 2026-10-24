"""Deployment checks for public submission throttling."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def check_rate_limit_cache(app_configs, **kwargs):
    alias = getattr(settings, "FORMS_WORKFLOWS_RATE_LIMIT_CACHE", "default")
    backend = settings.CACHES.get(alias, {}).get("BACKEND", "")
    if backend not in {
        "django.core.cache.backends.redis.RedisCache",
        "django.core.cache.backends.memcached.PyMemcacheCache",
        "django.core.cache.backends.memcached.PyLibMCCache",
        "django_redis.cache.RedisCache",
    }:
        return [
            Warning(
                "Public form rate limiting requires a shared cache with atomic add/incr.",
                hint="Configure Redis or Memcached and FORMS_WORKFLOWS_RATE_LIMIT_CACHE; local-memory caches only limit one process.",
                id="django_forms_workflows.W001",
            )
        ]
    return []
