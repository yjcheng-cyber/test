#!/usr/bin/env python3
"""Probe GitHub's artifact-v7 MIME validation from an Actions job."""

import os
import urllib.error

from gh_artifact import CANDIDATES, backend_ids, twirp


def main():
    results = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
    runtime = os.environ['ACTIONS_RUNTIME_TOKEN']
    run_id, job_id = backend_ids(runtime)
    for label, mime in CANDIDATES:
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
            print(f'[mime-probe] {label}: accepted={response.get("ok")}', flush=True)


if __name__ == '__main__':
    main()
