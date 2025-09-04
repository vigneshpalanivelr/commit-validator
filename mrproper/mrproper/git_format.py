#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import urllib.parse

from . import gitlab

HEADER = """\
:page_facing_up: git format report :page_facing_up:
===================================================

"""

INSTRUCTIONS_ON_ERRORS = """\

`git format` instructions available here:
https://wiki.sandvine.com/display/~kgrasman/git-format+for+packetlogic2

:bomb: **DO NOT RESOLVE THIS COMMENT WITHOUT FIXING THESE ISSUES** :bomb:<br>
It will be automatically resolved when they are fixed.<br>
If you believe the formatting done by `git format` is incorrect, add a response to this comment
detailing why it should not be followed after discussing it and reaching consensus. Then resolve
this comment manually. Also mention it on
[#tools-git-format](https://app.slack.com/client/T03E3SAPK/CN953SA01) slack channel
"""


def handle_mr(proj, mriid):
    mr = gitlab.gitlab("/projects/{}/merge_requests/{}"
                       .format(proj, mriid))

    mrcommits = gitlab.gitlab("/projects/{}/merge_requests/{}/commits"
                              .format(proj, mr.iid))

    errors = []
    with tempfile.TemporaryDirectory() as tdir:
        subprocess.call(["git", "init", "-q"], cwd=tdir)
        subprocess.call(["git", "fetch", "-q",
                         "--depth={}".format(max(len(mrcommits), 100)),
                         gitlab.get_clone_url(sys.argv[1]),
                         "merge-requests/{}/head".format(mr.iid)],
                        cwd=tdir)

        subprocess.check_output(["git", "checkout", "-q", "-b", "check", "FETCH_HEAD"], cwd=tdir)

        for commit in mrcommits:
            print("Checking out %s" % commit)
            subprocess.check_call(["git", "reset", "-q", "--hard", commit.id], cwd=tdir)
            subprocess.check_call(["git", "format", "--fixup"], cwd=tdir)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tdir)
            sha = sha.strip().decode("utf-8")
            if sha != commit.id:
                errors.append("* Commit {} `{}` contains formatting errors. Use 'git format'"
                              .format(commit.id[:9], commit.title))
                # subprocess.check_call(["git", "show", sha], cwd=tdir)

    if errors:
        must_not_be_resolved = True
        errors.append(INSTRUCTIONS_ON_ERRORS)
    else:
        must_not_be_resolved = False
        errors.append(":star: Everything seems fine! Way to go! :star:")

    gitlab.update_discussion(proj, mriid, HEADER,
                             "\n".join(errors), must_not_be_resolved)


def main():
    proj = urllib.parse.quote(sys.argv[1], safe="")
    mriid = int(sys.argv[2])
    handle_mr(proj, mriid)


if __name__ == '__main__':
    main()
