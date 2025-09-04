import json
import os
import pprint
import subprocess
import tornado.web


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
        checkers = checker.split("+")
        print(repr(checkers))

        if not all(c in ALLOWED_CHECKERS
                   for c in checkers):
            raise tornado.web.HTTPError(status_code=403)

        data = json_decode(self.request.body.decode("utf-8"))
        if data.object_kind == 'merge_request':
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

            print("CHANGES: %r" % changes)

            if data.user.username == "jenkins":
                print("Ignoring update from jenkins!")
            elif False and changes:
                print("MR EVENT SEEMED TO HAVE OTHER CHANGES: %r" % changes)
            else:
                print("Assuming branch changed")

                for c in checkers:
                    p = tornado.process.Subprocess([
                        "docker", "run", "-d", "--rm",
                        "--env-file", "mrproper.env",
                        "--log-driver=syslog",
                        "mr-checker-vp-test", c,
                        data.project.path_with_namespace,
                        str(data.object_attributes.iid)])
                yield p.wait_for_exit()
        self.finish("OK!")


routes = [
    (r'/mr-proper/(.*)', GitLabWebHookHandler),
]

settings = {
    'debug': True
}


app = tornado.web.Application(routes, **settings)


def main():
    assert os.path.isfile("mrproper.env")
    subprocess.check_call(["docker", "version"])
    print("Starting to listening...")
    app.listen(2)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
