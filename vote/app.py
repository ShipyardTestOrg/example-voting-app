from flask import Flask, render_template, request, make_response, g, jsonify
from redis import Redis
import os
import socket
import random
import json
import urllib.request
import ssl

option_a = os.getenv('OPTION_A', "Cats")
option_b = os.getenv('OPTION_B', "Dogs")
hostname = socket.gethostname()

app = Flask(__name__)

@app.route("/debug")
def debug_domains():
    """Debug endpoint to verify SHIPYARD_DOMAIN_* env vars and test inter-service connectivity."""
    # Collect all SHIPYARD_DOMAIN_* env vars
    domain_vars = {k: v for k, v in sorted(os.environ.items()) if k.startswith('SHIPYARD_DOMAIN')}

    # Check for problems
    problems = []
    for key, value in domain_vars.items():
        if 'None' in value:
            problems.append(f'{key} contains literal "None": {value}')
        if len(value) > 60 and '-' in value:
            # UUID pattern check (8-4-4-4-12)
            parts = value.split('.')[0].split('-')
            # Check if subdomain portion looks like it contains a UUID
            subdomain = value.split('.')[0]
            if len(subdomain) > 36:
                problems.append(f'{key} subdomain looks unusually long (possible UUID): {subdomain}')

    # Try to reach the result service via its SHIPYARD_DOMAIN
    connectivity = {}
    result_domain = os.environ.get('SHIPYARD_DOMAIN_RESULT')
    if result_domain:
        for protocol in ['https', 'http']:
            url = f'{protocol}://{result_domain}/'
            try:
                req = urllib.request.Request(url, method='GET')
                resp = urllib.request.urlopen(req, timeout=5)
                connectivity[f'{protocol}://{result_domain}'] = {
                    'status': resp.status,
                    'reachable': True,
                }
            except ssl.SSLCertVerificationError as e:
                connectivity[f'{protocol}://{result_domain}'] = {
                    'reachable': False,
                    'error_type': 'SSL_CERT_ERROR',
                    'error': str(e),
                }
            except Exception as e:
                connectivity[f'{protocol}://{result_domain}'] = {
                    'reachable': False,
                    'error_type': type(e).__name__,
                    'error': str(e),
                }

    return jsonify({
        'hostname': hostname,
        'domain_vars': domain_vars,
        'problems': problems,
        'connectivity': connectivity,
    })
    
def get_redis():
    if not hasattr(g, 'redis'):
        g.redis = Redis(host="redis", db=0, socket_timeout=5)
    return g.redis

@app.route("/", methods=['POST','GET'])
def hello():
    voter_id = request.cookies.get('voter_id')
    if not voter_id:
        voter_id = hex(random.getrandbits(64))[2:-1]

    vote = None

    if request.method == 'POST':
        redis = get_redis()
        vote = request.form['vote']
        data = json.dumps({'voter_id': voter_id, 'vote': vote})
        redis.rpush('votes', data)

    resp = make_response(render_template(
        'index.html',
        option_a=option_a,
        option_b=option_b,
        hostname=hostname,
        vote=vote,
    ))
    resp.set_cookie('voter_id', voter_id)
    return resp


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, debug=True, threaded=True)
