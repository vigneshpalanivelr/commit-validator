
import json
import os
import requests
import sys
import logging

GITLAB_HOST = 'git.internal.com'

# Get logger (will use the logger from logging_config if available, otherwise create simple logger)
logger = logging.getLogger(__name__)

# Helper for structured logging
class StructuredLog:
    """Lightweight structured logging helper."""
    @staticmethod
    def _fmt(msg, **kwargs):
        if kwargs:
            fields = ' '.join(f'{k}={v}' for k, v in kwargs.items())
            return f'{msg} | {fields}'
        return msg

    @staticmethod
    def debug(msg, **kwargs):
        logger.debug(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def info(msg, **kwargs):
        logger.info(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def warning(msg, **kwargs):
        logger.warning(StructuredLog._fmt(msg, **kwargs))

    @staticmethod
    def error(msg, **kwargs):
        logger.error(StructuredLog._fmt(msg, **kwargs))

slog = StructuredLog

try:
    GITLAB_ACCESS_TOKEN = os.environ['GITLAB_ACCESS_TOKEN']
    slog.info("GitLab access token loaded", token_prefix=GITLAB_ACCESS_TOKEN[:10])
except KeyError:
    slog.error("GITLAB_ACCESS_TOKEN environment variable not found")
    slog.error("Available environment variables", count=len(os.environ.keys()))
    raise


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
    url = f"https://{GITLAB_HOST}/api/v4{u}"

    slog.debug("Making GitLab API request", url=url, params=str(params))

    while True:
        try:
            r = requests.get(url, headers={'PRIVATE-TOKEN': GITLAB_ACCESS_TOKEN}, params=params)
            slog.debug("GitLab API response", status_code=r.status_code, url=url)

        except requests.exceptions.RequestException as e:
            slog.error("GitLab API request failed", error=str(e), url=url)
            raise

        if r.status_code == 401:
            slog.error("GitLab API unauthorized", status_code=401, host=GITLAB_HOST, token_prefix=GITLAB_ACCESS_TOKEN[:10])
            print("Sorry, unauthorized")
            sys.exit(1)

        if r.status_code not in (200, 201):
            try:
                error_detail = r.json()
                slog.error("GitLab API error", status_code=r.status_code, error=error_detail)
            except:
                slog.error("GitLab API error", status_code=r.status_code, response=r.text[:500])
            print("Unknown error %d" % r.status_code)
            print(r.json())
            sys.exit(1)

        if raw:
            slog.debug("Returning raw content", bytes=len(r.content))
            return r.content

        try:
            res = json.JSONDecoder(object_pairs_hook=AttrDict).decode(r.content.decode("utf-8"))
            slog.debug("JSON response parsed successfully")
        except json.JSONDecodeError as e:
            slog.error("Failed to parse JSON response", error=str(e), response=r.text[:500])
            raise

        if 'X-Total' in r.headers:
            # paginated
            slog.debug("Paginated response", total=r.headers['X-Total'])
            assert isinstance(res, list)
            accures.extend(res)
            res = accures
            if r.headers['X-Next-Page']:
                params['page'] = r.headers['X-Next-Page']
                slog.debug("Fetching next page", page=params['page'])
                continue

        slog.info("GitLab API request completed successfully", url=url)
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
    slog.info("Updating discussion for MR",
              project=proj,
              mr_iid=mriid,
              must_not_be_resolved=must_not_be_resolved)

    try:
        discussions = gitlab("/projects/{}/merge_requests/{}/discussions"
                           .format(proj, mriid))
        slog.debug("Found existing discussions", count=len(discussions))
    except Exception as e:
        slog.error("Failed to fetch discussions", error=str(e))
        raise

    body = header + body
    slog.debug("Full discussion body prepared", body_length=len(body))

    found_note = False
    for i, disc in enumerate(discussions):
        slog.debug("Checking discussion", discussion_num=f"{i+1}/{len(discussions)}", notes=len(disc.notes))
        for j, n in enumerate(disc.notes):
            if n.body.startswith(header):
                slog.info("Found existing note with matching header", discussion=i+1, note=j+1)
                found_note = True

                if n.resolved and must_not_be_resolved:
                    slog.info("Note is resolved but shouldn't be - unresolving")
                    unresolve_note(proj, mriid, disc.id, n.id)
                    print("RESOLVED BUT SHOULDN'T BE!")

                if n.body != body:
                    slog.info("Note content differs - updating")
                    update_note_body(proj, mriid, disc.id, n.id, body)
                    if not n.resolved and not must_not_be_resolved:
                        slog.info("Resolving note as validation passed")
                        resolve_note(proj, mriid, disc.id, n.id)
                else:
                    slog.info("Note content is identical - no update needed")
                    print("Already there!")
                break

    if not found_note:
        slog.info("No existing note found - creating new discussion")
        create_note(proj, mriid, body)

    slog.info("Discussion update completed")


def get_award_users(mr_proj, mr_iid):
    users = set()
    url = "projects/%s/merge_requests/%d/award_emoji" % (mr_proj, mr_iid)
    for award in gitlab(url):
        if award.name == 'thumbsup':
            users.add(award.user.name)
        else:
            print("Unknown award (%s) from %s" % (award.name, award.user.name))
    return users
