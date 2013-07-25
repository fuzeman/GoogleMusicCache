import os
import errno
import traceback
from flask import Flask, request, Response
from gevent.wsgi import WSGIServer
import requests
import time
from werkzeug.datastructures import Headers

app = Flask(__name__)
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
LOG_PATH = os.path.join(os.path.dirname(__file__), 'access.log')
LOG_FILE = open(LOG_PATH, 'a')


def create_directory(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def get_path(params):
    return os.path.join(CACHE_DIR, params['id'], params['range'])


def store(request, params):
    with open(get_path(params), 'wb') as f:
        f.write(request.content)

    with open(get_path(params) + '.headers', 'w') as f:
        for key, value in request.headers.items():
            if key in ['server', 'content-type', 'date', 'last-modified', 'x-content-type-options']:
                f.write(key + ': ' + value + '\n')


def exists(params):
    return os.path.exists(get_path(params))


def create_headers_from_cache(params):
    headers = {}
    with open(get_path(params) + '.headers', 'r') as f:
        for line in f.readlines():
            line = line.strip()
            key, value = line.split(': ')

            headers[key] = value

    return Headers(headers)


def create_response_from_cache(params):
    return Response(
        open(get_path(params), 'rb'),
        headers=create_headers_from_cache(params)
    )


def remove_from_dict(d, keys):
    for key in keys:
        if key in d:
            d.pop(key)
    return d


def proxy_request():
    try:
        url = 'http://' + request.url[request.url.index('/', request.url.index('http://') + 7) + 1:]
        print "proxy_request", url

        r = requests.get(
            url,
            headers=remove_from_dict(dict(request.headers.items()), [
                'Connection',
                'Host'
            ]),
            timeout=5
        )

        return Response(
            r.content,
            headers=remove_from_dict(dict(r.headers.items()), [
                'transfer-encoding',
                'content-encoding'
            ])
        )
    except requests.exceptions.Timeout:
        return Response('Gateway Timeout', status=504)


def log_request(cache_status, http_status, params):
    LOG_FILE.write("\t".join([
        time.time(),
        cache_status + '/' + str(http_status),
        params['id'],
        params['range']
    ]))


@app.route('/<host>/<path:path>')
def main(host, path):
    try:
        if path != 'videoplayback':
            return proxy_request()

        if 'id' not in request.args or 'range' not in request.args:
            return proxy_request()

        params = {
            'id': request.args.get('id'),

            'itag': request.args.get('itag'),
            'source': request.args.get('source'),
            'o': request.args.get('o'),
            'range': request.args.get('range'),
            'segment': request.args.get('segment'),
            'ratebypass': request.args.get('ratebypass'),

            'ip': request.args.get('ip'),
            'ipbits': request.args.get('ipbits'),

            'expire': request.args.get('expire'),
            'sparams': request.args.get('sparams'),

            'signature': request.args.get('signature'),
            'key': request.args.get('key'),

            'ms': request.args.get('ms'),
            'mt': request.args.get('mt'),
            'mv': request.args.get('mv'),
        }

        print params['id'], params['range']

        save_dir = os.path.join(CACHE_DIR, params['id'])
        create_directory(save_dir)

        if exists(params):
            log_request('TCP_HIT', 200, params)
            return create_response_from_cache(params)

        r = requests.get('http://' + host + '/' + path, params=params, headers={
            'User-Agent': request.headers['User-Agent']
        })

        print "response", '(' + str(r.status_code) + ')'

        if r.status_code == 200:
            store(r, params)

        log_request('TCP_MISS', r.status_code, params)
        return Response(r.content, headers=r.headers.items())
    except Exception, ex:
        print ex
        traceback.print_exc()
        raise ex


if __name__ == '__main__':
    create_directory(CACHE_DIR)
    print "CACHE_DIR", CACHE_DIR

    http_server = WSGIServer(('', 5000), app)
    http_server.serve_forever()
