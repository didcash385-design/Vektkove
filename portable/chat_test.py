#!/usr/bin/env python3
"""Local integration test for the cross-platform VKLINK text protocol."""
import socket
import subprocess
import sys
import threading
import os

binary = sys.argv[1]
environment = dict(os.environ)
environment["VEKTKOVE_CHAT_PASSPHRASE"] = "correct horse battery staple for tests"
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]

server = subprocess.Popen(
    [binary, "chat", "listen", "127.0.0.1", str(port)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", bufsize=1, env=environment,
)
try:
    waiting = server.stderr.readline()
    if "Waiting for one encrypted VKLINK/2 peer" not in waiting:
        raise RuntimeError(f"listener failed to start: {waiting!r}")
    client = subprocess.Popen(
        [binary, "chat", "connect", "127.0.0.1", str(port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1, env=environment,
    )
    client_out = []
    server_out = []
    client_received = threading.Event()
    server_received = threading.Event()

    def collect(stream, output, event, expected):
        for line in stream:
            output.append(line)
            if expected in line:
                event.set()

    client_reader = threading.Thread(target=collect, args=(client.stdout, client_out, client_received, "Peer: Grüß dich 🌍"))
    server_reader = threading.Thread(target=collect, args=(server.stdout, server_out, server_received, "Peer: out \"This is plain text, not executable code\""))
    client_reader.start()
    server_reader.start()
    server.stdin.write("Grüß dich 🌍\n")
    server.stdin.flush()
    client.stdin.write('out "This is plain text, not executable code"\n')
    client.stdin.flush()
    if not client_received.wait(timeout=10) or not server_received.wait(timeout=10):
        raise RuntimeError(f"chat message timeout; client={client_out!r}, server={server_out!r}")
    server.stdin.close()
    client.stdin.close()
    client_code = client.wait(timeout=10)
    server_code = server.wait(timeout=10)
    client_reader.join(timeout=3)
    server_reader.join(timeout=3)
    client_error = client.stderr.read()
    server_error = server.stderr.read()
    assert client_code == 0, (client_code, client_error)
    assert server_code == 0, (server_code, server_error)
    assert any("Peer: Grüß dich 🌍" in line for line in client_out), client_out
    assert any("Peer: out \"This is plain text, not executable code\"" in line for line in server_out), server_out
    assert any("You: out \"This is plain text, not executable code\"" in line for line in client_out), client_out
    print("VKLINK/2 encrypted UTF-8 chat test passed")
finally:
    for process in (server,):
        if process.poll() is None:
            process.kill()
            process.wait()

# A peer with the wrong passphrase must not authenticate or exchange messages.
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
server = subprocess.Popen(
    [binary, "chat", "listen", "127.0.0.1", str(port)],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", bufsize=1, env=environment,
)
try:
    if "Waiting for one encrypted VKLINK/2 peer" not in server.stderr.readline():
        raise RuntimeError("encrypted listener failed to start")
    wrong_environment = dict(environment)
    wrong_environment["VEKTKOVE_CHAT_PASSPHRASE"] = "different wrong passphrase"
    client = subprocess.Popen(
        [binary, "chat", "connect", "127.0.0.1", str(port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", bufsize=1, env=wrong_environment,
    )
    client_out, client_error = client.communicate(timeout=10)
    server_out, server_error = server.communicate(timeout=10)
    assert client.returncode != 0 and server.returncode != 0
    assert "authentication failed" in client_error.lower(), client_error
    assert "authentication failed" in server_error.lower(), server_error
    assert not client_out and not server_out, (client_out, server_out)
    print("VKLINK/2 wrong-passphrase authentication test passed")
finally:
    if server.poll() is None:
        server.kill()
        server.wait()
