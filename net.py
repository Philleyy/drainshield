"""
net.py: open web addresses (weather forecast, road routing) with an up-to-date list of trusted certificates
---------------------------------------------------------------------------------------------------------
Python checks every HTTPS site against a list of trusted certificate authorities. On Windows it reads that
list from the Windows certificate store, which can hold outdated entries: the site is fine, but Python
refuses it with "CERTIFICATE_VERIFY_FAILED ... certificate has expired". The certifi package carries
Mozilla's current list (it is installed with Streamlit), so we use it when it's there.
"""

import ssl
import urllib.request

try:
    import certifi
    CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:                                  # no certifi: fall back to the computer's own list
    CONTEXT = ssl.create_default_context()


def urlopen(url, timeout=10):
    """urllib.request.urlopen with certifi's certificates. url can be a string or a urllib Request."""
    return urllib.request.urlopen(url, timeout=timeout, context=CONTEXT)
