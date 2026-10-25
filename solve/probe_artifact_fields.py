#!/usr/bin/env python3
"""Check GitHub artifact version/MIME parsing with duplicate JSON field forms.

Runs in an owned GitHub Actions workflow. Never prints runtime credentials or
signed URLs. Accepted artifacts contain only a harmless marker body.
"""

import json
import os
import urllib.error
import urllib.request

from gh_artifact import backend_ids, twirp
from probe_v7_blob_type import rest_read


BASE = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
RUNTIME = os.environ['ACTIONS_RUNTIME_TOKEN']
RUN_ID, JOB_ID = backend_ids(RUNTIME)
SLUG = os.environ['GITHUB_REPOSITORY']
SERVICE = 'twirp/github.actions.results.api.v1.ArtifactService'
ODD = json.dumps('\u0085application/json')
VALID = json.dumps('application/json')
BODY = b'{"probe":"duplicate-artifact-fields"}'


def create_raw(name, fields):
    body = ('{' + ','.join((
        f'"workflow_run_backend_id":{json.dumps(RUN_ID)}',
        f'"workflow_job_run_backend_id":{json.dumps(JOB_ID)}',
        f'"name":{json.dumps(name)}',
        fields,
    )) + '}').encode()
    request = urllib.request.Request(
        BASE + SERVICE + '/CreateArtifact', data=body, method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {RUNTIME}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        return {'error': error.code, 'detail': error.read(180).decode('utf-8', 'replace')}


def upload(url):
    request = urllib.request.Request(url, data=BODY, method='PUT', headers={
        'x-ms-blob-type': 'BlockBlob',
        'x-ms-blob-content-type': '\u0085application/json',
        'Content-Length': str(len(BODY)),
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def main():
    cases = {
        'dupver67odd': f'"version":6,"version":7,"mime_type":{ODD}',
        'dupver76odd': f'"version":7,"version":6,"mime_type":{ODD}',
        'dupmimevalidodd': f'"version":7,"mime_type":{VALID},"mime_type":{ODD}',
        'dupmimeoddvalid': f'"version":7,"mime_type":{ODD},"mime_type":{VALID}',
        'aliasmimevalidodd': f'"version":7,"mime_type":{VALID},"mimeType":{ODD}',
        'aliasmimeoddvalid': f'"version":7,"mime_type":{ODD},"mimeType":{VALID}',
        'wrapperodd': f'"version":7,"mime_type":{{"value":{ODD}}}',
        'versionstr': f'"version":"6","mime_type":{ODD}',
    }
    for label, fields in cases.items():
        name = f'cassette-fields-{label}.json'
        result = create_raw(name, fields)
        if not result.get('ok'):
            print(label, 'create', result.get('error', result), result.get('detail', '')[:150])
            continue
        url = result['signed_upload_url']
        print(label, 'upload', upload(url))
        try:
            final = twirp(BASE, RUNTIME, 'FinalizeArtifact', {
                'workflow_run_backend_id': RUN_ID,
                'workflow_job_run_backend_id': JOB_ID,
                'name': name,
                'size': str(len(BODY)),
            })
        except urllib.error.HTTPError as error:
            print(label, 'finalize', error.code)
            continue
        if not final.get('ok'):
            print(label, 'finalize failed')
            continue
        print(label, 'artifact_id', final['artifact_id'], 'REST', rest_read(final['artifact_id'], BODY))


if __name__ == '__main__':
    main()
