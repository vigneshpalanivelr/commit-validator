import json
import os
import pprint
import subprocess
import tornado.web
import logging
import logging.handlers
import datetime


ALLOWED_CHECKERS = {
    'mrproper-clang-format',
    'mrproper-message',
    'rate-my-mr',
}


class AttrDict(dict):
    def __getattr__(self, attr):
        try:
            res = self[attr]
        except KeyError:
            raise AttributeError(attr)
        return res


def json_decode(d):
    return json.JSONDecoder(object_pairs_hook=AttrDict).decode(d)


class GitLabWebHookHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def post(self, checker):
        logger = logging.getLogger(__name__)
        request_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        request_id_short = request_id.split('_')[-1][:8]  # Use 8 chars for uniqueness
        
        logger.info(f"[{request_id_short}] === NEW WEBHOOK REQUEST ===")
        logger.info(f"[{request_id_short}] Requested checkers: {checker}")
        
        checkers = checker.split("+")
        logger.info(f"[{request_id_short}] Parsed checkers: {checkers}")
        logger.info(f"[{request_id_short}] Allowed checkers: {ALLOWED_CHECKERS}")

        invalid_checkers = [c for c in checkers if c not in ALLOWED_CHECKERS]
        if invalid_checkers:
            logger.error(f"[{request_id_short}] Invalid checkers requested: {invalid_checkers}")
            raise tornado.web.HTTPError(status_code=403)

        try:
            data = json_decode(self.request.body.decode("utf-8"))
            logger.info(f"[{request_id_short}] Successfully parsed webhook JSON")
        except Exception as e:
            logger.error(f"[{request_id_short}] Failed to parse webhook JSON: {e}")
            raise tornado.web.HTTPError(status_code=400)

        if data.object_kind == 'merge_request':
            logger.info(f"[{request_id_short}] Processing MR event")
            logger.info(f"[{request_id_short}] Project: {data.project.path_with_namespace}")
            logger.info(f"[{request_id_short}] MR IID: {data.object_attributes.iid}")
            logger.info(f"[{request_id_short}] MR Title: {data.object_attributes.title}")
            logger.info(f"[{request_id_short}] User: {data.user.username}")
            
            print("v= MR EVENT " + "=" * 50)
            pprint.pprint(data)
            print("^= MR EVENT " + "=" * 50)
            
            changes = dict(data.changes)
            try:
                del changes['total_time_spent']
            except KeyError:
                pass
            try:
                del changes['updated_at']
            except KeyError:
                pass

            logger.info(f"[{request_id_short}] Changes detected: {changes}")

            if data.user.username == "jenkins":
                logger.info(f"[{request_id_short}] Ignoring update from jenkins user")
            elif False and changes:
                logger.info(f"[{request_id_short}] MR has other changes, skipping: {changes}")
            else:
                logger.info(f"[{request_id_short}] Processing validation for {len(checkers)} checkers")

                for i, c in enumerate(checkers):
                    logger.info(f"[{request_id_short}] Starting checker {i+1}/{len(checkers)}: {c}")

                    # Get configuration from environment
                    log_dir = os.environ.get('LOG_DIR', '/home/docker/tmp/mr-validator-logs')
                    log_level = os.environ.get('LOG_LEVEL', 'DEBUG')
                    log_max_bytes = os.environ.get('LOG_MAX_BYTES', '52428800')
                    log_backup_count = os.environ.get('LOG_BACKUP_COUNT', '3')
                    log_structure = os.environ.get('LOG_STRUCTURE', 'organized')

                    # Get AI/LLM configuration
                    gitlab_token = os.environ.get('GITLAB_ACCESS_TOKEN', '')
                    bfa_host = os.environ.get('BFA_HOST', '')
                    bfa_token_key = os.environ.get('BFA_TOKEN_KEY', '')
                    ai_service_url = os.environ.get('AI_SERVICE_URL', '')
                    api_timeout = os.environ.get('API_TIMEOUT', '120')

                    logger.debug(f"[{request_id_short}] Env vars to pass: BFA_HOST={bfa_host if bfa_host else 'NOT_SET'} AI_SERVICE_URL={ai_service_url if ai_service_url else 'NOT_SET'} API_TIMEOUT={api_timeout}")

                    docker_cmd = [
                        "docker", "run", "-d", "--rm",
                        # Context variables
                        "--env", f"REQUEST_ID={request_id}",
                        "--env", f"PROJECT_ID={data.project.path_with_namespace}",
                        "--env", f"MR_IID={data.object_attributes.iid}",
                        # GitLab configuration
                        "--env", f"GITLAB_ACCESS_TOKEN={gitlab_token}",
                        # AI/LLM configuration (BFA_HOST takes priority)
                        "--env", f"BFA_HOST={bfa_host}",
                        "--env", f"BFA_TOKEN_KEY={bfa_token_key}",
                        "--env", f"AI_SERVICE_URL={ai_service_url}",
                        "--env", f"API_TIMEOUT={api_timeout}",
                        # Logging configuration
                        "--env", f"LOG_DIR={log_dir}",
                        "--env", f"LOG_LEVEL={log_level}",
                        "--env", f"LOG_MAX_BYTES={log_max_bytes}",
                        "--env", f"LOG_BACKUP_COUNT={log_backup_count}",
                        "--env", f"LOG_STRUCTURE={log_structure}",
                        "--log-driver=syslog",
                        # Mount log directory
                        "--volume", f"{log_dir}:{log_dir}",
                        "--name", f"mr-{c}-{data.object_attributes.iid}-{request_id_short}",
                        "mr-checker-vp-test", c,
                        data.project.path_with_namespace,
                        str(data.object_attributes.iid)
                    ]
                    
                    logger.info(f"[{request_id_short}] Docker command: {' '.join(docker_cmd)}")
                    
                    try:
                        p = tornado.process.Subprocess(docker_cmd)
                        yield p.wait_for_exit()
                        
                        if p.returncode == 0:
                            logger.info(f"[{request_id_short}] Checker {c} container started successfully")
                        else:
                            logger.error(f"[{request_id_short}] Checker {c} container failed to start, return code: {p.returncode}")
                            
                    except Exception as e:
                        logger.error(f"[{request_id_short}] Failed to start checker {c}: {e}")
                
                logger.info(f"[{request_id_short}] All checkers launched")
        else:
            logger.info(f"[{request_id_short}] Non-MR event, ignoring: {data.object_kind}")
            
        logger.info(f"[{request_id_short}] === WEBHOOK REQUEST COMPLETED ===")
        self.finish("OK!")


routes = [
    (r'/mr-proper/(.*)', GitLabWebHookHandler),
]

settings = {
    'debug': True
}


app = tornado.web.Application(routes, **settings)


def main():
    # Ensure log directory exists
    os.makedirs('/home/docker/tmp/mr-validator-logs', exist_ok=True)

    # Setup logging with rotation (100 MB per file, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        '/home/docker/tmp/mr-validator-logs/webhook-server.log',
        maxBytes=100 * 1024 * 1024,  # 100 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler]
    )
    logger = logging.getLogger(__name__)

    logger.info("=== MR Validator Webhook Server Starting ===")
    logger.info(f"Current working directory: {os.getcwd()}")

    # Verify environment variables are loaded (via --env-file at container start)
    required_env_vars = ['GITLAB_ACCESS_TOKEN']
    optional_env_vars = ['BFA_HOST', 'AI_SERVICE_URL', 'LOG_DIR', 'LOG_LEVEL', 'API_TIMEOUT']

    logger.info("Checking environment variables:")
    for var in required_env_vars:
        value = os.environ.get(var)
        if value:
            logger.info(f"  ✓ {var} = {value[:15]}..." if len(value) > 15 else f"  ✓ {var} = {value}")
        else:
            logger.error(f"  ✗ {var} = NOT SET (REQUIRED!)")
            raise EnvironmentError(f"Required environment variable {var} is not set")

    for var in optional_env_vars:
        value = os.environ.get(var)
        if value:
            # Mask sensitive values
            if 'TOKEN' in var or 'KEY' in var:
                logger.info(f"  ✓ {var} = {value[:15]}...")
            else:
                logger.info(f"  ✓ {var} = {value}")
        else:
            logger.info(f"  - {var} = NOT SET (optional)")

    try:
        subprocess.check_call(["docker", "version"])
        logger.info("Docker connectivity verified")
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker connectivity failed: {e}")
        raise

    logger.info("Starting webhook server on port 9912...")
    app.listen(9912)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
