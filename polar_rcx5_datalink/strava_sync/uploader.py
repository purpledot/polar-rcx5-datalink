from io import BytesIO

import requests
from requests.exceptions import HTTPError

from polar_rcx5_datalink.exceptions import StravaUnauthorized, StravaActivityUploadError


def upload_activity(token, tcx_as_bytestring, **kwargs):
    """Uploads a new data file to create an activity from"""
    url = 'https://www.strava.com/api/v3/uploads'
    activity_file = BytesIO(tcx_as_bytestring)

    resp = requests.post(
        url,
        files={'file': activity_file},
        headers={'Authorization': f'Bearer {token}'},
        data={'data_type': 'tcx', **kwargs},
    )

    return handle_response(resp)


def handle_response(resp):
    try:
        resp.raise_for_status()
    except HTTPError as err:
        try:
            msg = err.response.json()
        except ValueError:
            msg = ''

        if err.response.status_code == 401:
            exc_class = StravaUnauthorized
        else:
            exc_class = StravaActivityUploadError

        raise exc_class('{} {}'.format(err, msg), response=resp)

    return resp.json()
