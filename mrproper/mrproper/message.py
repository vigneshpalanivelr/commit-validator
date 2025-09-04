#!/usr/bin/env python3

import configparser
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

from . import gitlab

HEADER = """\
:mag_right: commit message check report :mag:
=============================================

"""


def get_config(checkoutdir):
    confpath = os.path.join(checkoutdir, ".mr-proper.conf")
    conf = configparser.ConfigParser()
    if os.path.exists(confpath):
        conf.read(confpath)
    return conf


def parse_tag_and_ticket_from_subject(subject):
    m = re.match(r'([A-Z]*)(?:\(([-A-Z0-9, #]+)\))?:(.*)', subject)
    if not m:
        return None, None, subject
    return m.group(1), m.group(2), m.group(3)


def looks_like_a_real_name(name):
    return len(name.split()) > 1 or name[0].isupper()


def handle_mr(proj, mriid):
    thumbs_in_gitlab = gitlab.get_award_users(proj, mriid)

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

        config = get_config(tdir)

        valid_tags = set(config.get("message", "valid_tags",
                                    fallback="BUG,FEATURE,IMPROVEMENT,REFACTOR").split(","))
        valid_tags_without_ticket = set(config.get("message", "valid_tags_without_ticket",
                                                   fallback="IMPROVEMENT,REFACTOR").split(","))

        commits_with_no_reviewedby = 0
        for commit in mrcommits:
            commiterrors = []
            d = subprocess.check_output(["git", "cat-file", "commit", commit.id], cwd=tdir)
            d = d.decode("utf-8")
            hdrs, body = d.split("\n\n", 1)
            body = body

            lines = body.split("\n")

            subject = lines[0]

            reg = re.compile(r'^(author|committer) (?P<name>.+) <(?P<email>.+)> .*$', re.MULTILINE)
            for match in reg.findall(hdrs):
                what, name, _email = match
                if not looks_like_a_real_name(name):
                    commiterrors.append(f'{what} "{name}" does not look like a real name')

            tag, tickets, rest = parse_tag_and_ticket_from_subject(subject)
            if tag is None:
                commiterrors.append("Commit subject not properly tagged")
            else:
                if tag not in valid_tags:
                    commiterrors.append("Commit subject tag '%s' is not valid" % tag)
                if tickets is None and tag not in valid_tags_without_ticket:
                    commiterrors.append("Commit subject tag '%s' need a bug ticket" % tag)
                if rest[0] != ' ':
                    commiterrors.append("Commit subject should have space after 'TAG: '")
                else:
                    m = re.match(r' (\[[^\]]*\])(.*)', rest)
                    if m:
                        rest = m.group(2)

                m = re.match(r' [^A-Z]', rest)
                if m:
                    commiterrors.append("Commit subject should "
                                        "start with capital letter")

            if subject.strip()[-1] == '.':
                commiterrors.append("Commit subject should "
                                    "NOT end with period (.)")

            if subject.strip() != subject:
                commiterrors.append("Commit subject has extra whitespace")

            if len(subject) > 76:
                commiterrors.append("Commit subject should be at most "
                                    "76 columns wide")

            reviewers = set()
            if len(lines) > 1:
                if lines[1] != "":
                    commiterrors.append("Commit should "
                                        "have an empty line between subject and body")

                for l in lines[2:]:
                    if len(l) > 72 and l[:2] != "  ":
                        commiterrors.append("Commit message body should "
                                            "be wrapped at 72 columns")
                        break

                for l in lines:
                    if l.strip() == "Reviewed-By:":
                        commiterrors.append("Commit should not contain empty 'Reviewed-By' trailer")
                    elif l.startswith("Reviewed-By: "):
                        reviewer = l[len("Reviewed-By: "):]

                        # falsehoods programmers believe about names
                        if not looks_like_a_real_name(reviewer):
                            commiterrors.append("'{}' doesn't look like a real reviewer"
                                                .format(reviewer))
                        elif reviewer in reviewers:
                            commiterrors.append("'{}' was mentioned twice in Reviewed-By"
                                                .format(reviewer))
                        else:
                            reviewers.add(reviewer)

            if not reviewers:
                commits_with_no_reviewedby += 1

            print(reviewers)
            print(thumbs_in_gitlab)
            missing_thumbs = set(reviewers) - thumbs_in_gitlab
            if missing_thumbs:
                commiterrors.append("The following persons were mentioned "
                                    "in 'Reviewed-By' trailers, but did not give "
                                    "a thumbs up on the MR: {}"
                                    .format(", ".join(sorted(missing_thumbs))))

            errors.append((commit, commiterrors))

    import pprint
    pprint.pprint(errors)

    must_not_be_resolved = False
    lines = []
    lines.append("| Commit | Status |")
    lines.append("|--------|--------|")
    for commit, commiterrors in errors:
        if not commiterrors:
            lines.append("|{}<br>`{}`|:white_check_mark:|"
                         .format(commit.short_id, commit.title))
        else:
            must_not_be_resolved = True
            lines.append("|{}<br>`{}`|<ul>{}</ul>|"
                         .format(commit.short_id, commit.title,
                                 "".join("<li>{}</li>".format(e)
                                         for e in commiterrors)))

    if commits_with_no_reviewedby > 0:
        must_not_be_resolved = True
        lines.append("")
        lines.append(":warning: **{} commit{} are missing `Reviewed-By` trailer.** :warning:<br />"
                     .format(commits_with_no_reviewedby,
                             "s" if commits_with_no_reviewedby > 1 else ""))
        lines.append("Merging this MR will not be possible until those are added.")
        lines.append("")
        if thumbs_in_gitlab:
            lines.append("*Hint: Use `git gitlab-apply-reviewers`*")
        else:
            lines.append("*Hint: Get reviewer to do :+1: on the MR "
                         "then run `git gitlab-apply-reviewers`*")

    gitlab.update_discussion(proj, mriid, HEADER,
                             "\n".join(lines), must_not_be_resolved)


def main():
    proj = urllib.parse.quote(sys.argv[1], safe="")
    mriid = int(sys.argv[2])
    handle_mr(proj, mriid)


if __name__ == "__main__":
    main()
