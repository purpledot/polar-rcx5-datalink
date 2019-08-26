from requests.exceptions import HTTPError


class PolarDataLinkError(Exception):
    """An ambiguous error occurred."""


class SyncError(PolarDataLinkError):
    """An error occurred while synchronizing the watch."""


class ParserError(PolarDataLinkError):
    """An error occurred while parsing training session."""


class ConverterError(PolarDataLinkError):
    """An error occurred while converting training session."""


class StravaHTTPError(PolarDataLinkError, HTTPError):
    """An HTTP error occurred."""


class StravaUnauthorized(StravaHTTPError):
    """An authorization is needed to upload training sessions to Strava."""


class StravaActivityUploadError(StravaHTTPError):
    """An HTTP error occurred while uploading training session to Strava."""
