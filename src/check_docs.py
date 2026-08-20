# Copyright (c) 2025 Heinz Nixdorf Institute
# Copyright (c) 2025 Paderborn University
# Copyright (c) 2025 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License, Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# SPDX-License-Identifier: Apache-2.0
"""Checks the links and images in the documentation.

Usage:  python src/check_docs.py [directory]

The README is the KIT. A table of contents that leads nowhere is the first
thing a reader meets, and it is invisible to every other check in this
repository - the file is valid Markdown either way.

Two kinds of reference are followed:

    file references     an image or a document that is not there
    heading anchors     a link into this document whose heading does not exist

The anchor rule is the one GitHub applies, and it holds a trap. Punctuation is
removed but the spaces around it are not, so a heading written

    ## Use Case / Domain Explanation

becomes "use-case--domain-explanation" with two hyphens, not one. Five links
in the README were written with one and led nowhere.
"""
import glob
import io
import os
import re
import sys
import urllib.parse


def anchor(heading):
    """The identifier GitHub gives a heading.

    Lower case, punctuation removed, spaces turned into hyphens - each space
    on its own. Repeated hyphens are not collapsed, which is the whole point.
    """
    text = heading.strip().lower()
    text = re.sub(r'`([^`]*)`', r'\1', text)          # code spans keep their text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)   # links keep their label
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE)
    return text.replace(' ', '-')


# Directories that are not part of the repository. node_modules alone holds
# several hundred readme files of other projects, and their broken links are
# none of our business.
UEBERGANGEN = ('node_modules', '.git', '__pycache__', 'nodered', 'export',
               'jobs', '.venv', 'venv')


def gehoert_dazu(pfad):
    teile = os.path.normpath(pfad).split(os.sep)
    return not any(t in UEBERGANGEN for t in teile)


def check(basis):
    dateien = sorted(d for d in set(
        glob.glob(os.path.join(basis, '*.md'))
        + glob.glob(os.path.join(basis, '**', '*.md'), recursive=True))
        if gehoert_dazu(d))
    funde = []
    for pfad in dateien:
        text = io.open(pfad, encoding='utf-8').read()
        ordner = os.path.dirname(pfad) or '.'
        anker = {anchor(h) for h in re.findall(r'^#+\s+(.+?)\s*$', text, re.M)}
        ziele = (re.findall(r'\]\(([^)\s]+)\)', text)
                 + re.findall(r'src="([^"]+)"', text))
        for ziel in ziele:
            if ziel.startswith(('http://', 'https://', 'mailto:')):
                continue
            if ziel.startswith('#'):
                if ziel[1:] not in anker:
                    funde.append('%s: no heading for %s' % (pfad, ziel))
                continue
            # A space in a path is written %20. Without decoding, every such
            # link looks broken.
            rein = urllib.parse.unquote(ziel.split('#')[0])
            if not rein:
                continue
            if not os.path.exists(os.path.normpath(os.path.join(ordner, rein))):
                funde.append('%s: %s does not exist' % (pfad, ziel))
    return dateien, funde


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('--help', '-h', '/?'):
        print(__doc__.strip())
        return 0
    basis = sys.argv[1] if len(sys.argv) > 1 else '.'
    dateien, funde = check(basis)
    for f in funde:
        print('    %s' % f)
    print('%d documents, %d findings' % (len(dateien), len(funde)))
    return 1 if funde else 0


if __name__ == '__main__':
    sys.exit(main())
