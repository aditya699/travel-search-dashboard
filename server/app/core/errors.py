"""Typed errors, so callers can tell a bad key from a bad page from a bad config."""


class AppError(Exception):
    """Base class for every error this project raises on purpose."""


class ConfigError(AppError):
    """A config file or setting is missing or malformed."""


class ScrapeError(AppError):
    """A page could not be fetched, or the site's robots.txt does not allow it."""


class LLMError(AppError):
    """The language model call failed after the SDK's own retries."""


class LLMRefusalError(LLMError):
    """The model declined the request."""


class PublishError(AppError):
    """A Power BI REST call failed."""
