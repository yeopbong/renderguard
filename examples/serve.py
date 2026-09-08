"""Serve original reproducible demonstration pages on loopback."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == '__main__':
    handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).parent.resolve()))
    print('Example pages: http://127.0.0.1:9030')
    ThreadingHTTPServer(('127.0.0.1', 9030), handler).serve_forever()
