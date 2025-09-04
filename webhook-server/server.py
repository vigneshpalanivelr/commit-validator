import json
import os
import pprint
import subprocess
import tornado.web
import logging
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
                    
                    docker_cmd = [
                        "docker", "run", "-d", "--rm",
                        "--env-file", "mrproper.env",
                        "--log-driver=syslog",
                        "--volume", "/home/docker/tmp/mr-validator-logs:/home/docker/tmp/mr-validator-logs",
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
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('/home/docker/tmp/mr-validator-logs/webhook-server.log'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("=== MR Validator Webhook Server Starting ===")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Environment file check: mrproper.env exists = {os.path.isfile('mrproper.env')}")
    
    if not os.path.isfile("mrproper.env"):
        logger.error("ERROR: mrproper.env file not found!")
        logger.error("Current directory contents:")
        for item in os.listdir('.'):
            logger.error(f"  - {item}")
        raise FileNotFoundError("mrproper.env file is required")
    
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
