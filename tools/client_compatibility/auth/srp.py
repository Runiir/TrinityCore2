"""Classic Battle.net SRP v2, derived from TrinityCore SRP6 (GPL-2.0-or-later).

The signed PBKDF2 exponent and extra evidence padding intentionally match the
pinned implementation, rather than a generic RFC 5054 SRP library.
"""
import hashlib
import hmac
import secrets

N = int("AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050A"
        "37329CBB4A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD50E"
        "8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE82918A9962F0B93B855"
        "F97993EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B14773BCA"
        "97B43A23FB801676BD207A436C6481F1D2B9078717461A5B9D32E688F8774854"
        "4523B524B0D57D5EA77A2775D2ECFA032CFBDBF52FB3786160279004E57AE6AF"
        "874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9DBFBB694"
        "B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73", 16)
G = 2
K = int.from_bytes(hashlib.sha256(N.to_bytes(256, "big") + G.to_bytes(256, "big")).digest(), "big")


def username(login):
    return hashlib.sha256(login.upper().encode()).hexdigest().upper()


def exponent(login, password, salt):
    raw = hashlib.pbkdf2_hmac("sha512", (username(login) + ":" + password).encode(), salt, 15000, 64)
    return int.from_bytes(raw, "big", signed=True) % (N - 1)


def verifier(login, password, salt):
    return pow(G, exponent(login, password, salt), N)


def evidence(*values):
    # TrinityCore GetBrokenEvidenceVector adds one zero byte at byte boundaries.
    return hashlib.sha256(b"".join(value.to_bytes((value.bit_length() + 8) >> 3, "big") for value in values)).digest()


class Challenge:
    def __init__(self, login, salt, value):
        self.login, self.salt, self.v = login, salt, value
        self.b = secrets.randbelow(N - 2) + 1
        self.B = (pow(G, self.b, N) + K * self.v) % N
        self.used = False

    def json(self):
        return {"version": 2, "iterations": 15000, "modulus": format(N, "X"), "generator": "02",
                "hash_function": "SHA-256", "username": username(self.login),
                "salt": self.salt.hex().upper(), "public_B": format(self.B, "X")}

    def verify(self, public_a, client_m1):
        if self.used:
            return None
        self.used = True
        if not 0 < public_a < N or len(client_m1) > 64:
            return None
        u = int.from_bytes(hashlib.sha256(public_a.to_bytes(256, "big") + self.B.to_bytes(256, "big")).digest(), "big")
        if not u:
            return None
        secret = pow(public_a * pow(self.v, u, N), self.b, N)
        expected = evidence(public_a, self.B, secret)
        try:
            supplied = int(client_m1, 16).to_bytes(32, "big")
        except (ValueError, OverflowError):
            return None
        if not hmac.compare_digest(expected, supplied):
            return None
        return evidence(public_a, int.from_bytes(expected, "big"), secret).hex().upper()
