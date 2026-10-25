#!/usr/bin/env python3
"""Check whether same-name artifact creation mixes v6/v7 MIME metadata."""

import os
import urllib.error

from gh_artifact import backend_ids, put_blob, twirp, verify


def main():
    base = os.environ['ACTIONS_RESULTS_URL'].rstrip('/') + '/'
    runtime = os.environ['ACTIONS_RUNTIME_TOKEN']
    run_id, job_id = backend_ids(runtime)
    slug = os.environ['GITHUB_REPOSITORY']
    variants = [(6, '\u0085application/json'), (7, 'application/json')]
    for scenario, versions in enumerate((variants, variants[::-1]), 1):
        name = f'rc-version-recreate-{scenario}.json'
        urls = []
        for version, mime in versions:
            request = {
                'workflow_run_backend_id': run_id,
                'workflow_job_run_backend_id': job_id,
                'name': name,
                'version': version,
                'mime_type': mime,
            }
            try:
                response = twirp(base, runtime, 'CreateArtifact', request)
            except urllib.error.HTTPError as error:
                print(f'[{scenario}] Create v{version}: HTTP {error.code} '
                      f'{error.read()[:180]!r}', flush=True)
                break
            print(f'[{scenario}] Create v{version}: ok={response.get("ok")}',
                  flush=True)
            if not response.get('ok'):
                break
            urls.append((version, mime, response['signed_upload_url']))
        if not urls:
            continue
        body = b'{}'
        for version, mime, url in urls:
            try:
                status = put_blob(url, body, 'application/json')
            except urllib.error.HTTPError as error:
                status = error.code
            print(f'[{scenario}] Upload through v{version} URL: {status}', flush=True)
        try:
            final = twirp(base, runtime, 'FinalizeArtifact', {
                'workflow_run_backend_id': run_id,
                'workflow_job_run_backend_id': job_id,
                'name': name,
                'size': str(len(body)),
            })
        except urllib.error.HTTPError as error:
            print(f'[{scenario}] Finalize: HTTP {error.code} '
                  f'{error.read()[:180]!r}', flush=True)
            continue
        print(f'[{scenario}] Finalize: {final}', flush=True)
        if final.get('ok'):
            verify(slug, int(final['artifact_id']), body)


if __name__ == '__main__':
    main()
