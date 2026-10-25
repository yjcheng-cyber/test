#!/usr/bin/env python3
"""Test whether an artifact v7 blob's Content-Type can override REST MIME.

Runs only in a GitHub Actions job. Prints no runtime token or signed URL.
"""

import os
import urllib.error
import urllib.parse
import urllib.request

from gh_artifact import backend_ids, twirp, SERVICE


BASE = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
RUNTIME = os.environ['ACTIONS_RUNTIME_TOKEN']
RUN_ID, JOB_ID = backend_ids(RUNTIME)
SLUG = os.environ['GITHUB_REPOSITORY']
API_TOKEN = os.environ['GH_API_TOKEN']
BODY = b'{"probe":"artifact-v7-blob-type"}'
ODD = '\u0085application/json'


def call(method, data):
    return twirp(BASE, RUNTIME, method, {
        'workflow_run_backend_id': RUN_ID,
        'workflow_job_run_backend_id': JOB_ID,
        **data,
    })


def put(url, mime):
    request = urllib.request.Request(url, data=BODY, method='PUT', headers={
        'x-ms-blob-type': 'BlockBlob',
        'x-ms-blob-content-type': mime,
        'Content-Length': str(len(BODY)),
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return f'{error.code}: {error.read(150)!r}'


def set_properties(url, mime):
    suffix = '&' if urllib.parse.urlsplit(url).query else '?'
    request = urllib.request.Request(url + suffix + 'comp=properties', data=b'', method='PUT', headers={
        'x-ms-blob-content-type': mime,
        'x-ms-version': '2023-11-03',
        'Content-Length': '0',
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return f'{error.code}: {error.read(150)!r}'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


def rest_read(artifact_id):
    request = urllib.request.Request(
        f'https://api.github.com/repos/{SLUG}/actions/artifacts/{artifact_id}/zip',
        headers={
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'https://github.com/sindresorhus/gh-got',
            'Authorization': f'token {API_TOKEN}',
        },
    )
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=30)
        return 'no redirect'
    except urllib.error.HTTPError as error:
        if error.code != 302:
            return f'API {error.code}'
        location = error.headers['Location']
        rsct = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query).get('rsct')
    try:
        with urllib.request.urlopen(urllib.request.Request(location), timeout=30) as response:
            return f'rsct={rsct!r} type={response.headers.get("Content-Type")!r} body_match={response.read() == BODY}'
    except urllib.error.HTTPError as error:
        return f'download {error.code}'


def main():
    for label, first_mime, change_after in (
        ('put_odd', ODD, False),
        ('properties_odd', 'application/json', True),
    ):
        name = f'cassette-v7-{label}.json'
        created = call('CreateArtifact', {
            'name': name, 'version': 7, 'mime_type': 'application/json',
        })
        if not created.get('ok'):
            print(label, 'create failed')
            continue
        url = created['signed_upload_url']
        print(label, 'put', put(url, first_mime))
        final = call('FinalizeArtifact', {'name': name, 'size': str(len(BODY))})
        if not final.get('ok'):
            print(label, 'finalize failed')
            continue
        artifact_id = final['artifact_id']
        print(label, 'artifact_id', artifact_id)
        if change_after:
            print(label, 'set properties', set_properties(url, ODD))
        print(label, 'REST', rest_read(artifact_id))


if __name__ == '__main__':
    main()
