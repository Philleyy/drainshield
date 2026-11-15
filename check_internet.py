"""
check_internet.py: why can't Python reach the weather and routing websites?
Run:  python check_internet.py     and paste what it prints.
"""
import os
import ssl
import sys
import tempfile
import time
import urllib.request

SITES = ["api.open-meteo.com", "router.project-osrm.org", "www.google.com"]
print("Python", sys.version.split()[0], "| OpenSSL", ssl.OPENSSL_VERSION)
print("Computer clock:", time.strftime("%Y-%m-%d %H:%M"))
try:
    import certifi
    print("certifi", certifi.__version__, certifi.where())
except ImportError:
    certifi = None
    print("certifi: NOT INSTALLED")

for host in SITES:
    print(f"\n== {host}")
    # 1. Who signed the certificate this computer receives? (read without checking it)
    try:
        pem = ssl.get_server_certificate((host, 443), timeout=8)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
            f.write(pem)
        info = ssl._ssl._test_decode_cert(f.name)
        os.unlink(f.name)
        issuer = ", ".join(v for part in info["issuer"] for k, v in part if k in ("organizationName", "commonName"))
        print("  certificate issued by:", issuer)
        print("  valid until:", info["notAfter"])
    except Exception as e:
        print("  could not read the certificate:", repr(e))
    # 2. Does it pass with Windows' list, and with certifi's list?
    for name, ctx in [("Windows list", ssl.create_default_context()),
                      ("certifi list", ssl.create_default_context(cafile=certifi.where()) if certifi else None)]:
        if ctx is None:
            continue
        try:
            with urllib.request.urlopen(f"https://{host}/", timeout=8, context=ctx) as r:
                print(f"  {name}: OK")
        except urllib.error.HTTPError:
            print(f"  {name}: OK (connected; the page itself answered with an error, that's fine)")
        except Exception as e:
            print(f"  {name}: FAILED: {getattr(e, 'reason', e)}")
