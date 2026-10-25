#!/usr/bin/env python3
"""Check whether artifact names alter the signed download response type."""

import os
import urllib.error

from gh_artifact import backend_ids, put_blob, twirp


def main():
    results = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
    runtime = os.environ['ACTIONS_RUNTIME_TOKEN']
    run_id, job_id = backend_ids(runtime)
    names = (
        'name-amp&rsct=%C2%85application%2Fjson',
        'name-encoded%26rsct%3D%C2%85application%2Fjson',
    )
    for name in names:
        request = {
            'workflow_run_backend_id': run_id,
            'workflow_job_run_backend_id': job_id,
            'name': name,
            'version': 6,
            'mime_type': '\u0085application/json',
        }
        try:
            created = twirp(results, runtime, 'CreateArtifact', request)
            if not created.get('ok'):
                print(f'[name-probe] {name}: create returned {created}', flush=True)
                continue
            put_blob(created['signed_upload_url'], b'{}', 'application/json')
            final = twirp(results, runtime, 'FinalizeArtifact', {
                'workflow_run_backend_id': run_id,
                'workflow_job_run_backend_id': job_id,
                'name': name, 'size': '2',
            })
            print(f'[name-probe] {name}: artifact_id={final.get("artifact_id")}', flush=True)
        except urllib.error.HTTPError as error:
            print(f'[name-probe] {name}: HTTP {error.code} {error.read()[:180]!r}', flush=True)


if __name__ == '__main__':
    main()
