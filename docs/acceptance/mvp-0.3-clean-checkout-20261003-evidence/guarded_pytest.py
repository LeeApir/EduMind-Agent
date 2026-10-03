import socket, pytest
import app.core.provider_factory as factory

def forbidden(*args, **kwargs):
    raise AssertionError('Provider construction forbidden in clean-checkout verification')
factory.build_default_provider_gateway=forbidden
original=socket.socket.connect

def connect(sock,address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1'):
        raise AssertionError('External network forbidden')
    return original(sock,address)
socket.socket.connect=connect
raise SystemExit(pytest.main(['-q','tests/test_catalog_publication.py','tests/test_catalog_sessions.py','tests/test_catalog_quiz.py','tests/test_catalog_demo.py','tests/test_catalog_exports.py','tests/test_catalog_mode.py']))
