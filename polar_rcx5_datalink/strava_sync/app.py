import time
import urllib.parse
import threading
import functools

import click
import requests
from flask import Flask, flash, render_template, session, request, redirect, url_for

from .uploader import upload_activity
from polar_rcx5_datalink.converter import TCXConverter
from polar_rcx5_datalink.exceptions import (
    StravaActivityUploadError,
    ParsingSamplesError,
)
from polar_rcx5_datalink.utils import print_error

STRAVA_OAUTH_URL = 'https://www.strava.com/oauth'
SPORT_PROFILES = ('Other', 'Running', 'Biking')
DEFAULT_SPORT = SPORT_PROFILES[1]


def open_browser(host, port):
    url = f'http://{host}:{port}'
    while True:
        try:
            requests.get(url)
            break
        except Exception:
            time.sleep(0.5)

    click.launch(url)


def auth_url(client_id):
    params = {
        'client_id': client_id,
        'redirect_uri': url_for('strava_authorized', _external=True),
        'response_type': 'code',
        'scope': 'write',
    }

    return f'{STRAVA_OAUTH_URL}/authorize?{urllib.parse.urlencode(params)}'


def run_app(host, port, client_id, client_secret, training_sessions):
    app = Flask(__name__)
    app.secret_key = b'cT![\x88\xd8JN1x{S\xb2\xc7]\x18'

    def authorized():
        return 'access_token' in session

    def upload_training_sessions(ids):
        selected = (ts for ts in training_sessions if ts.id in ids)
        for training_session in selected:
            ts_id = training_session.id
            sport = request.form.get(f'sport-{ts_id}')

            try:
                converter = TCXConverter(training_session, sport)
            except ParsingSamplesError:
                print_error(f"Error parsing samples of session #{ts_id}")
                continue

            try:
                upload_activity(
                    session['access_token'], converter.tostring(), external_id=ts_id
                )
            except StravaActivityUploadError as err:
                # Hack to check if activity is a duplicate.
                # In case if we don't want to interupt the flow because of it.
                duplicate = 'duplicate' in str(err)
                if not duplicate:
                    print_error(f"Can't upload training session {ts_id}. {err}")

    @app.route('/', methods=['GET', 'POST'])
    def index():
        if not authorized():
            return redirect(url_for('authorization'))

        if request.method == 'POST':
            selected_ids = request.form.getlist('training_sessions')
            if selected_ids:
                upload_training_sessions(selected_ids)
                flash('Activities have been successfully uploaded')
            else:
                flash('Please select training sessions you want to upload', 'error')

            return redirect(url_for('index'))

        return render_template(
            'index.html',
            sport_profiles=SPORT_PROFILES,
            default_sport=DEFAULT_SPORT,
            training_sessions=training_sessions,
        )

    @app.route('/authorization', methods=['GET', 'POST'])
    def authorization():
        if authorized():
            return redirect(url_for('index'))

        return render_template('authorization.html', auth_url=auth_url(client_id))

    @app.route('/strava-authorized')
    def strava_authorized():
        code = request.args.get('code')
        if code is None:
            return redirect(url_for('index'))

        params = {'client_id': client_id, 'client_secret': client_secret, 'code': code}
        resp = requests.post(f'{STRAVA_OAUTH_URL}/token', params=params)

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            try:
                msg = err.response.json()
            except ValueError:
                msg = ''

            print_error(f'{err} {msg}')
            flash('An error occurred while trying to obtain access token', 'error')
        else:
            session['access_token'] = resp.json()['access_token']

        return redirect(url_for('authorization'))

    threading.Thread(target=functools.partial(open_browser, host, port)).start()
    app.run(host=host, port=port)
