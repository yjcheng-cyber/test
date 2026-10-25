#!/usr/bin/env python3
"""Probe GitHub's artifact-v7 MIME validation from an Actions job."""

import os
import urllib.error

from gh_artifact import CANDIDATES, backend_ids, put_blob, twirp

EXTRA = [
    ('percent-85-suffix', 'application/json%85'),
    ('percent-85-prefix', '%85application/json'),
    ('percent-c285-prefix', '%C2%85application/json'),
    ('percent-1c-prefix', '%1capplication/json'),
    ('comma-prefix', '\u0085application/json,application/json'),
    ('comma-suffix', 'application/json,\u0085application/json'),
]


def main():
    results = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
    runtime = os.environ['ACTIONS_RUNTIME_TOKEN']
    run_id, job_id = backend_ids(runtime)
    for label, mime in CANDIDATES + EXTRA:
        request = {
            'workflow_run_backend_id': run_id,
            'workflow_job_run_backend_id': job_id,
            'name': f'mime-probe-{label}.json',
            'version': 7,
            'mime_type': mime,
        }
        try:
            response = twirp(results, runtime, 'CreateArtifact', request)
        except urllib.error.HTTPError as error:
            print(f'[mime-probe] {label}: HTTP {error.code} {error.read()[:180]!r}', flush=True)
        else:
            if not response.get('ok'):
                print(f'[mime-probe] {label}: unexpected response={response}', flush=True)
                continue
            put_blob(response['signed_upload_url'], b'{}', 'application/json')
            final = twirp(results, runtime, 'FinalizeArtifact', {
                'workflow_run_backend_id': run_id,
                'workflow_job_run_backend_id': job_id,
                'name': request['name'], 'size': '2',
            })
            print(f'[mime-probe] {label}: accepted artifact_id={final.get("artifact_id")}', flush=True)

    for version in (-1, 0, 5, 8, 9):
        request = {
            'workflow_run_backend_id': run_id,
            'workflow_job_run_backend_id': job_id,
            'name': f'version-probe-{version}.json',
            'version': version,
            'mime_type': '\u0085application/json',
        }
        try:
            response = twirp(results, runtime, 'CreateArtifact', request)
        except urllib.error.HTTPError as error:
            print(f'[version-probe] {version}: HTTP {error.code} {error.read()[:180]!r}', flush=True)
            continue
        if not response.get('ok'):
            print(f'[version-probe] {version}: unexpected response={response}', flush=True)
            continue
        put_blob(response['signed_upload_url'], b'{}', 'application/json')
        final = twirp(results, runtime, 'FinalizeArtifact', {
            'workflow_run_backend_id': run_id,
            'workflow_job_run_backend_id': job_id,
            'name': request['name'], 'size': '2',
        })
        print(f'[version-probe] {version}: accepted artifact_id={final.get("artifact_id")}', flush=True)


if __name__ == '__main__':
    main()
