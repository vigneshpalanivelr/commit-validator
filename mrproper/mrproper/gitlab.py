
import json
import os
import requests
import sys


GITLAB_HOST = 'git.internal.com'
GITLAB_ACCESS_TOKEN = os.environ['GITLAB_ACCESS_TOKEN']


def get_clone_url(proj):
    return ("https://oauth:{}@{}/{}.git"
            .format(GITLAB_ACCESS_TOKEN, GITLAB_HOST, proj))


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            res = self[attr]
        except KeyError:
            raise AttributeError(attr)
        return res


def gitlab(u, params=None, raw=False):
    params = {} if params is None else params.copy()
    accures = []
    while True:
        r = requests.get("https://%s/api/v4/%s" % (GITLAB_HOST, u),
                         headers={'PRIVATE-TOKEN': GITLAB_ACCESS_TOKEN},
                         params=params)
        if r.status_code == 401:
            print("Sorry, unauthorized")
            sys.exit(1)
        if r.status_code not in (200, 201):
            print("Unknown error %d" % r.status_code)
            print(r.json())
            sys.exit(1)

        if raw:
            return r.content
        res = json.JSONDecoder(object_pairs_hook=AttrDict).decode(r.content.decode("utf-8"))
        if 'X-Total' in r.headers:
            # paginated
            assert isinstance(res, list)
            accures.extend(res)
            res = accures
            if r.headers['X-Next-Page']:
                params['page'] = r.headers['X-Next-Page']
                continue

        return res


def _update_note(proj, mriid, discid, noteid, data):
    r = requests.put("https://{}/api/v4/projects/{}/merge_requests/{}/discussions/{}/notes/{}"
                     .format(GITLAB_HOST,
                             proj, mriid, discid, noteid),
                     headers={'PRIVATE-TOKEN': GITLAB_ACCESS_TOKEN},
                     json=data)
    if r.status_code not in (200, 201):
        print("Unknown error %d" % r.status_code)
        print(r.json())
        sys.exit(1)


def update_note_body(proj, mriid, discid, noteid, body):
    _update_note(proj, mriid, discid, noteid, {'body': body})


def resolve_note(proj, mriid, discid, noteid):
    _update_note(proj, mriid, discid, noteid, {'resolved': True})


def unresolve_note(proj, mriid, discid, noteid):
    _update_note(proj, mriid, discid, noteid, {'resolved': False})


def create_note(proj, mriid, body):
    r = requests.post("https://{}/api/v4/projects/{}/merge_requests/{}/discussions"
                      .format(GITLAB_HOST,
                              proj, mriid),
                      headers={'PRIVATE-TOKEN': GITLAB_ACCESS_TOKEN},
                      json={
                          'body': body
                      })
    if r.status_code not in (200, 201):
        print("Unknown error %d" % r.status_code)
        print(r.json())
        sys.exit(1)


def update_discussion(proj, mriid, header, body, must_not_be_resolved):
    discussions = gitlab("/projects/{}/merge_requests/{}/discussions"
                         .format(proj, mriid))

    # pprint.pprint(discussions)

    body = header + body

    found_note = False
    for disc in discussions:
        for n in disc.notes:
            if n.body.startswith(header):
                if n.resolved and must_not_be_resolved:
                    unresolve_note(proj, mriid, disc.id, n.id)
                    print("RESOLVED BUT SHOULDN'T BE!")
                if n.body != body:
                    update_note_body(proj, mriid, disc.id, n.id, body)
                    if not n.resolved and not must_not_be_resolved:
                        resolve_note(proj, mriid, disc.id, n.id)
                else:
                    print("Already there!")
                found_note = True
                break

    if not found_note:
        create_note(proj, mriid, body)


def get_award_users(mr_proj, mr_iid):
    users = set()
    url = "projects/%s/merge_requests/%d/award_emoji" % (mr_proj, mr_iid)
    for award in gitlab(url):
        if award.name == 'thumbsup':
            users.add(award.user.name)
        else:
            print("Unknown award (%s) from %s" % (award.name, award.user.name))
    return users
