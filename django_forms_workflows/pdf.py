"""PDF resources are offline by default, including CSS and SVG subresources."""

import base64
import binascii

from django.conf import settings


def safe_pdf_url_fetcher(url, *args, **kwargs):
    """Allow bounded embedded raster images; never open files or network URLs.

    Logos/signatures should be embedded as data:image/png;base64,... (or JPEG).
    A deployment needing additional resources can supply a reviewed fetcher via
    FORMS_WORKFLOWS_PDF_URL_FETCHER. It must enforce its own allowlist and limits.
    """
    limit = getattr(settings, "FORMS_WORKFLOWS_PDF_MAX_RESOURCE_BYTES", 5 * 1024 * 1024)
    if len(url) > limit * 4 // 3 + 128:
        raise ValueError("PDF resource exceeds size limit")
    header, sep, encoded = url.partition(",")
    if not sep or header not in ("data:image/png;base64", "data:image/jpeg;base64"):
        raise ValueError("PDF resource URL is not permitted")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid PDF image") from exc
    mime = header[5:].split(";")[0]
    signature = b"\x89PNG\r\n\x1a\n" if mime == "image/png" else b"\xff\xd8\xff"
    if len(data) > limit or not data.startswith(signature):
        raise ValueError("Invalid PDF image")
    return {"string": data, "mime_type": mime}


def pdf_url_fetcher():
    from django.utils.module_loading import import_string

    custom = getattr(settings, "FORMS_WORKFLOWS_PDF_URL_FETCHER", None)
    if custom:
        factory = import_string(custom)
        return factory()
    # WeasyPrint 70 replaced dictionary-returning callables with URLFetcher.
    try:
        from weasyprint.urls import URLFetcher, URLFetcherResponse
    except ImportError:
        return safe_pdf_url_fetcher

    class OfflineFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            resource = safe_pdf_url_fetcher(url)
            return URLFetcherResponse(
                url, resource["string"], {"Content-Type": resource["mime_type"]}
            )

    return OfflineFetcher(allowed_protocols={"data"}, allow_redirects=False)
