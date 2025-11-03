
import json
import os
import requests
import sys
import logging


GITLAB_HOST = 'git.internal.com'

# Ensure log directory exists
os.makedirs('/home/docker/tmp/mr-validator-logs', exist_ok=True)

# Get REQUEST_ID from environment (passed from webhook server)
REQUEST_ID = os.environ.get('REQUEST_ID', 'unknown')
REQUEST_ID_SHORT = REQUEST_ID.split('_')[-1][:8] if REQUEST_ID != 'unknown' else 'unknown'

# Generate unique log filename per container (using REQUEST_ID for correlation)
container_id = os.environ.get('HOSTNAME', 'unknown')
log_filename = f'/home/docker/tmp/mr-validator-logs/gitlab-api-{REQUEST_ID_SHORT}-{container_id}.log'

# Setup logging with REQUEST_ID in format
logging.basicConfig(
    level=logging.DEBUG,
    format=f'%(asctime)s - [{REQUEST_ID_SHORT}] - %(filename)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    GITLAB_ACCESS_TOKEN = os.environ['GITLAB_ACCESS_TOKEN']
    logger.info(f"GitLab access token loaded (starts with: {GITLAB_ACCESS_TOKEN[:10]}...)")
except KeyError:
    logger.error("GITLAB_ACCESS_TOKEN environment variable not found!")
    logger.error("Available environment variables:")
    for key in sorted(os.environ.keys()):
        logger.error(f"  {key}")
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

    logger.info(f"Making GitLab API request: {url}")
    logger.debug(f"Parameters: {params}")

    while True:
        try:
            r = requests.get(url, headers={'PRIVATE-TOKEN': GITLAB_ACCESS_TOKEN}, params=params)
            logger.info(f"GitLab API response: {r.status_code} for {url}")

        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab API request failed: {e}")
            logger.error(f"URL: {url}")
            raise

        if r.status_code == 401:
            logger.error("GitLab API: Unauthorized (401)")
            logger.error(f"Token being used: {GITLAB_ACCESS_TOKEN[:10]}...")
            logger.error(f"Host: {GITLAB_HOST}")
            print("Sorry, unauthorized")
            sys.exit(1)

        if r.status_code not in (200, 201):
            logger.error(f"GitLab API error {r.status_code}")
            try:
                error_detail = r.json()
                logger.error(f"Error details: {error_detail}")
            except:
                logger.error(f"Raw response: {r.text}")
            print("Unknown error %d" % r.status_code)
            print(r.json())
            sys.exit(1)

        if raw:
            logger.info(f"Returning raw content ({len(r.content)} bytes)")
            return r.content

        try:
            res = json.JSONDecoder(object_pairs_hook=AttrDict).decode(r.content.decode("utf-8"))
            logger.debug(f"Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {r.text[:500]}")
            raise

        if 'X-Total' in r.headers:
            # paginated
            logger.info(f"Paginated response, total: {r.headers['X-Total']}")
            assert isinstance(res, list)
            accures.extend(res)
            res = accures
            if r.headers['X-Next-Page']:
                params['page'] = r.headers['X-Next-Page']
                logger.info(f"Fetching next page: {params['page']}")
                continue

        logger.info(f"GitLab API request completed successfully")
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
    logger.info(f"Updating discussion for MR {mriid} in project {proj}")
    logger.info(f"Header: {header[:50]}...")
    logger.info(f"Must not be resolved: {must_not_be_resolved}")

    try:
        discussions = gitlab("/projects/{}/merge_requests/{}/discussions"
                           .format(proj, mriid))
        logger.info(f"Found {len(discussions)} existing discussions")
    except Exception as e:
        logger.error(f"Failed to fetch discussions: {e}")
        raise

    body = header + body
    logger.debug(f"Full discussion body length: {len(body)} characters")

    found_note = False
    for i, disc in enumerate(discussions):
        logger.debug(f"Checking discussion {i+1}/{len(discussions)}, notes: {len(disc.notes)}")
        for j, n in enumerate(disc.notes):
            if n.body.startswith(header):
                logger.info(f"Found existing note with matching header in discussion {i+1}, note {j+1}")
                found_note = True

                if n.resolved and must_not_be_resolved:
                    logger.info("Note is resolved but shouldn't be - unresolving")
                    unresolve_note(proj, mriid, disc.id, n.id)
                    print("RESOLVED BUT SHOULDN'T BE!")

                if n.body != body:
                    logger.info("Note content differs - updating")
                    update_note_body(proj, mriid, disc.id, n.id, body)
                    if not n.resolved and not must_not_be_resolved:
                        logger.info("Resolving note as validation passed")
                        resolve_note(proj, mriid, disc.id, n.id)
                else:
                    logger.info("Note content is identical - no update needed")
                    print("Already there!")
                break

    if not found_note:
        logger.info("No existing note found - creating new discussion")
        create_note(proj, mriid, body)

    logger.info("Discussion update completed")


def get_award_users(mr_proj, mr_iid):
    users = set()
    url = "projects/%s/merge_requests/%d/award_emoji" % (mr_proj, mr_iid)
    for award in gitlab(url):
        if award.name == 'thumbsup':
            users.add(award.user.name)
        else:
            print("Unknown award (%s) from %s" % (award.name, award.user.name))
    return users
