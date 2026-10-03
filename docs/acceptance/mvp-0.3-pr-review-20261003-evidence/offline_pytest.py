import socket,pytest
original=socket.socket.connect

def guard(sock,address):
 if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1'):
  raise AssertionError('External connections forbidden during offline PR review')
 return original(sock,address)
socket.socket.connect=guard
raise SystemExit(pytest.main(['-q']))
