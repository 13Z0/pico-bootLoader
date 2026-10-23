#!/usr/bin/env python3
"""
Writes the fixtures compare.py runs updateAll.py and ua_host against:
configurations with made-up sets of random files (no real ROMs), their zips,
download databases, and the files the test HTTP server serves.

Usage: make_fixtures.py <output dir> <http port>
"""

import hashlib
import json
import os
import random
import struct
import sys
import zipfile
import zlib

OUT, PORT = sys.argv[1], int(sys.argv[2])
URL = f"http://127.0.0.1:{PORT}"
random.seed(20261008)


def blob(n):
    return bytes(random.getrandbits(8) for _ in range(n))


def crc(data):
    return "%08x" % (zlib.crc32(data) & 0xFFFFFFFF)


def write(path, data):
    path = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def make_zip(path, entries, method=zipfile.ZIP_DEFLATED):
    path = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", method) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


def corrupt_entry(path, name):
    """Flips a byte of a stored entry's data; the directory keeps its CRC."""
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(name)
    with open(path, "r+b") as f:
        f.seek(info.header_offset + 26)
        name_len, extra_len = struct.unpack("<HH", f.read(4))
        f.seek(info.header_offset + 30 + name_len + extra_len)
        b = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([b[0] ^ 0xFF]))


def files_of(prefix, n, size=1024):
    return {f"{prefix}{i}": blob(size + i) for i in range(1, n + 1)}


def core(cid, zips, dest, files, name=None):
    return {
        "id": cid, "name": name or cid.capitalize(), "set": f"test set {cid}",
        "zips": zips, "destination": dest,
        "files": [{"name": k, "size": len(v), "crc": crc(v)} for k, v in files.items()],
    }


local = []      # sets installed from zips in the zip folder

# Flat zip, stored on disk under an upper-case name.
alpha = files_of("a", 4)
make_zip("zips/ALPHA.ZIP", list(alpha.items()))
local.append(core("alpha", ["alpha.zip"], "/roms/ALPHA", alpha))

# Merged zip: a renamed file at the root, a clone subfolder with a file of
# its own, a duplicate of a root file and a variant under a root name.
beta = files_of("b", 5)
make_zip("zips/beta.zip", [
    ("b1", beta["b1"]), ("b2", beta["b2"]), ("b3", beta["b3"]), ("b4.renamed", beta["b4"]),
    ("betaj/", b""), ("betaj/b5", beta["b5"]), ("betaj/b2", beta["b2"]), ("betaj/b1", blob(1025)),
])
local.append(core("beta", ["beta.zip"], "\\roms\\arcade\\BETA\\", beta))

# Split set: the clone zip first, the parent second.
gamma = files_of("g", 3)
make_zip("zips/gammac.zip", [("g3", gamma["g3"])])
make_zip("zips/gamma.zip", [("g1", gamma["g1"]), ("g2", gamma["g2"])])
local.append(core("gamma", ["gammac.zip", "gamma.zip"], "roms/arcade/GAMMA", gamma))

# A file the zip does not have.
delta = files_of("d", 3)
make_zip("zips/delta.zip", [("d1", delta["d1"]), ("d2", delta["d2"])])
local.append(core("delta", ["delta.zip"], "/roms/DELTA", delta))

# A file of the expected name with other contents.
eps = files_of("e", 2)
make_zip("zips/eps.zip", [("e1", eps["e1"]), ("e2", blob(len(eps["e2"])))])
local.append(core("eps", ["eps.zip"], "/roms/EPS", eps))

# A damaged entry: its data no longer matches the CRC in the directory.
zeta = files_of("z", 2)
corrupt_entry(make_zip("zips/zeta.zip", list(zeta.items()), zipfile.ZIP_STORED), "z1")
local.append(core("zeta", ["zeta.zip"], "/roms/ZETA", zeta))

# A zip that is not there at all, and one that is not a zip.
local.append(core("eta", ["eta.zip"], "/roms/ETA", files_of("h", 2)))
write("zips/xi.zip", b"this is not a zip file")
local.append(core("xi", ["xi.zip"], "/roms/XI", files_of("x", 2)))

with open(os.path.join(OUT, "cfg_local.json"), "w") as f:
    json.dump({"cores": local}, f, indent=2)

# A card on which part of alpha is already right and one file is wrong.
write("card_partial/roms/ALPHA/a1", alpha["a1"])
write("card_partial/roms/ALPHA/a2", alpha["a2"])
write("card_partial/roms/ALPHA/a3", blob(10))
write("card_partial/roms/ALPHA/other.txt", b"left alone")

# ---------------------------------------------------------------------------
# Download databases
# ---------------------------------------------------------------------------

remote = []
db_files = {}


def serve(path, data):
    write(os.path.join("srv", path), data)
    return f"{URL}/{path}"


def zip_bytes(entries):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


def md5(data):
    return hashlib.md5(data).hexdigest()


# Downloaded and installed.
theta = files_of("t", 3)
data = zip_bytes(list(theta.items()))
db_files["games/mame/theta.zip"] = {"url": serve("files/theta.zip", data),
                                    "size": len(data), "hash": md5(data).upper()}
remote.append(core("theta", ["theta.zip"], "/roms/THETA", theta))

# Wrong MD5, wrong size, not found, and a file that is not a zip.
iota = files_of("i", 1)
data = zip_bytes(list(iota.items()))
db_files["games/mame/iota.zip"] = {"url": serve("files/iota.zip", data), "size": len(data),
                                   "hash": "0" * 32}
remote.append(core("iota", ["iota.zip"], "/roms/IOTA", iota))

lam = files_of("l", 1)
data = zip_bytes(list(lam.items()))
db_files["games/mame/lam.zip"] = {"url": serve("files/lam.zip", data), "size": len(data) + 1}
remote.append(core("lam", ["lam.zip"], "/roms/LAM", lam))

kappa = files_of("k", 1)
db_files["games/mame/kappa.zip"] = {"url": f"{URL}/files/missing/kappa.zip"}
remote.append(core("kappa", ["kappa.zip"], "/roms/KAPPA", kappa))

nu = files_of("n", 1)
data = b"not a zip, although size and MD5 match"
db_files["games/mame/nu.zip"] = {"url": serve("files/nu.zip", data), "size": len(data),
                                 "hash": md5(data)}
remote.append(core("nu", ["nu.zip"], "/roms/NU", nu))

# Listed under hbmame first, with other contents, and under mame, both
# without a url, so that base_files_url and quoting are used.
mu = files_of("m", 2)
wrong = zip_bytes([("m1", blob(len(mu["m1"]))), ("m2", mu["m2"])])
right = zip_bytes(list(mu.items()))
serve("files/games/hbmame/mu set.zip", wrong)
serve("files/games/mame/mu set.zip", right)
db_files["games/hbmame/mu set.zip"] = {"size": len(wrong), "hash": md5(wrong)}
db_files["|games/mame/mu set.zip"] = {"size": len(right), "hash": md5(right)}
remote.append(core("mu", ["mu set.zip"], "/roms/arcade/MU", mu))

# In the database, but already in the zip folder, so not downloaded.
omicron = files_of("o", 2)
make_zip("zips/omicron.zip", list(omicron.items()))
db_files["games/mame/omicron.zip"] = {"url": f"{URL}/files/missing/omicron.zip"}
remote.append(core("omicron", ["omicron.zip"], "/roms/OMICRON", omicron))

# In no database.
remote.append(core("pi", ["pi.zip"], "/roms/PI", files_of("p", 1)))

db = {"db_id": "test_db", "base_files_url": f"{URL}/files/", "files": db_files}
db_text = json.dumps(db, indent=1).encode()
serve("db.json", db_text)
serve("db.json.zip", zip_bytes([("db.json", db_text)]))
serve("nofiles.json", json.dumps({"db_id": "x"}).encode())
serve("broken.json", b"{ this is not json")
write("db_local.json", json.dumps({"files": db_files}).encode())   # no db_id: the path is shown
write("db_zipped.json.zip", zip_bytes([("readme.txt", b"x"), ("sub/db.json", db_text)]))
write("db_nojson.zip", zip_bytes([("readme.txt", b"x")]))

with open(os.path.join(OUT, "cfg_db.json"), "w") as f:
    json.dump({"databases": [f"{URL}/db.json.zip"], "cores": remote}, f, indent=2)
with open(os.path.join(OUT, "cfg_dbfile.json"), "w") as f:
    json.dump({"databases": ["db_local.json"], "cores": remote}, f, indent=2)
with open(os.path.join(OUT, "cfg_nodb.json"), "w") as f:
    json.dump({"cores": remote}, f, indent=2)

# ---------------------------------------------------------------------------
# Configurations read from a config_url
# ---------------------------------------------------------------------------

# The served configuration has other sets and a database the local one lacks,
# and a config_url of its own that must not be followed.
remote_cfg = serve("cfg_remote.json", json.dumps(
    {"config_url": f"{URL}/no-such-cfg.json", "databases": [f"{URL}/db.json.zip"],
     "cores": remote}, indent=2).encode())
for name, url in (("fetch", remote_cfg), ("fetch404", f"{URL}/no-such-cfg.json"),
                  ("fetchbroken", f"{URL}/broken.json"), ("fetchnocores", f"{URL}/nofiles.json"),
                  ("fetchoff", "")):
    with open(os.path.join(OUT, f"cfg_{name}.json"), "w") as f:
        json.dump({"config_url": url, "cores": local}, f, indent=2)

# ---------------------------------------------------------------------------
# Game data: one URL per entry, a zip or a plain file
# ---------------------------------------------------------------------------


def data_entry(did, url, dest, files, archives=None, uf2=None):
    entry = {"id": did, "name": did.capitalize() + " data", "set": f"test data {did}",
             "url": url, "destination": dest,
             "files": [{"name": k, "size": len(v), "crc": crc(v)} for k, v in files.items()]}
    if archives is not None:
        entry["archives"] = archives
    if uf2 is not None:
        entry["uf2"] = uf2
    return entry


def uf2_image(data, address, family):
    """The UF2 file picotool's "uf2 convert -t bin -o <address> --family <family>"
    writes (checked against picotool with doom1.whx): 512-byte blocks of 256 data
    bytes, zero-filled."""
    blocks = -(-len(data) // 256)
    image = bytearray(512 * blocks)
    for n in range(blocks):
        struct.pack_into("<IIIIIIII", image, 512 * n, 0x0A324655, 0x9E5D5157, 0x2000,
                         address + 256 * n, 256, n, blocks, family)
        image[512 * n + 32:512 * n + 32 + 256] = data[256 * n:256 * n + 256].ljust(256, b"\0")
        struct.pack_into("<I", image, 512 * n + 508, 0x0AB16F30)
    return bytes(image)


def sfx_bytes(entries):
    """A self-extracting archive: an exe stub, then a zip whose offsets count
    from the start of the file, as in the Duke Nukem 3D shareware package."""
    import io
    buf = io.BytesIO()
    buf.write(b"MZ" + blob(3000))
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    data = buf.getvalue()
    eocd = data.rfind(b"PK\x05\x06")
    cd_size, cd_offset = struct.unpack("<II", data[eocd + 12:eocd + 20])
    assert cd_offset == eocd - cd_size, "offsets must be absolute"
    return data


game = []

# A plain file, kept in the zip folder under its URL's (unquoted) name and
# installed under another one.
rho = {"rho.uf2": blob(3000)}
serve("data/rho file.uf2", rho["rho.uf2"])
game.append(data_entry("rho", f"{URL}/data/rho%20file.uf2", "/roms/RHO", rho))

# A zip whose files go into subfolders of the destination; one file of the zip
# is not wanted. The URL has a query.
sigma = {"base/s1": blob(2000), "base/sub/s2": blob(2001), "readme.txt": b"sigma readme"}
data = zip_bytes([("roms/sigma/base/s1", sigma["base/s1"]),
                  ("roms/sigma/base/sub/s2", sigma["base/sub/s2"]),
                  ("roms/sigma/readme.txt", sigma["readme.txt"]),
                  ("unwanted.txt", b"not installed")])
game.append(data_entry("sigma", serve("data/sigma.zip", data) + "?download=1", "/roms/SIGMA",
                       sigma))
make_zip("zips_data/sigma.zip", [(f"roms/sigma/{k}", v) for k, v in sigma.items()])
write("zips_data/rho file.uf2", rho["rho.uf2"])

# A zip holding a self-extracting archive that holds the data; the licence is
# in both.
tau = {"TAU.GRP": blob(5000), "LICENSE.TXT": b"tau licence"}
inner = sfx_bytes(list(tau.items()))
data = zip_bytes([("LICENSE.TXT", tau["LICENSE.TXT"]), ("INSTALL.EXE", blob(500)),
                  ("TAU.SHR", inner)])
game.append(data_entry("tau", serve("data/tau13.zip", data), "/roms/TAU", tau, ["tau.shr"]))

# A plain file installed as a UF2 image, its last block only partly used.
omega_raw = blob(1000)
serve("data/omega.whx", omega_raw)
game.append(data_entry("omega", f"{URL}/data/omega.whx", "/roms/OMEGA",
                       {"omega.uf2": uf2_image(omega_raw, 0x10200000, 0xE48BFF58)},
                       uf2={"address": "0x10200000", "family": "e48bff58"}))
write("zips_data/omega.whx", omega_raw)

# The same file, but the image the configuration expects is at another address.
serve("data/omegabad.whx", omega_raw)
game.append(data_entry("omegabad", f"{URL}/data/omegabad.whx", "/roms/OMEGABAD",
                       {"omega.uf2": uf2_image(omega_raw, 0x10400000, 0xE48BFF58)},
                       uf2={"address": "0x10200000", "family": "e48bff58"}))

# Not found; a plain file with other contents; a zip without the named
# archive; and a named archive that is not a zip.
game.append(data_entry("upsilon", f"{URL}/data/missing/upsilon.uf2", "/roms/UPSILON",
                       {"upsilon.uf2": blob(100)}))
phi = {"phi.bin": blob(100)}
serve("data/phi.bin", blob(100))
game.append(data_entry("phi", f"{URL}/data/phi.bin", "/roms/PHI", phi))
chi = {"CHI.GRP": blob(100)}
serve("data/chi.zip", zip_bytes([("CHI.GRP.txt", b"x")]))
game.append(data_entry("chi", f"{URL}/data/chi.zip", "/roms/CHI", chi, ["CHI.SHR"]))
psi = {"PSI.GRP": blob(100)}
serve("data/psi.zip", zip_bytes([("sub/PSI.SHR", b"MZ not a zip")]))
game.append(data_entry("psi", f"{URL}/data/psi.zip", "/roms/PSI", psi, ["psi.shr"]))

with open(os.path.join(OUT, "cfg_data.json"), "w") as f:
    json.dump({"databases": [f"{URL}/db.json.zip"], "cores": [remote[0]], "data": game}, f,
              indent=2)

# A card on which part of sigma is already right and one file is wrong.
write("card_data_partial/roms/SIGMA/base/s1", sigma["base/s1"])
write("card_data_partial/roms/SIGMA/readme.txt", b"edited")

# ---------------------------------------------------------------------------
# Invalid configurations
# ---------------------------------------------------------------------------

good = core("ok", ["ok.zip"], "/roms/OK", files_of("q", 1))


def bad(name, cfg):
    with open(os.path.join(OUT, f"bad_{name}.json"), "w") as f:
        f.write(cfg if isinstance(cfg, str) else json.dumps(cfg))


bad("syntax", '{"cores": [ }')
bad("nocores", {"cores": []})
bad("missing_key", {"cores": [{k: v for k, v in good.items() if k != "files"}]})
bad("twice", {"cores": [good, dict(good, id="OK")]})
bad("dest", {"cores": [dict(good, destination="/roms/../x")]})
bad("dest_empty", {"cores": [dict(good, destination="//")]})
bad("nozips", {"cores": [dict(good, zips=[])]})
bad("zipname", {"cores": [dict(good, zips=["a/b.zip"])]})
bad("filename", {"cores": [dict(good, files=[{"name": "x:y", "size": 1, "crc": "0"}])]})
bad("crc", {"cores": [dict(good, files=[{"name": "x", "size": 1, "crc": "xyz"}])]})
bad("size", {"cores": [dict(good, files=[{"name": "x", "size": "big", "crc": "0"}])]})
bad("databases", {"databases": "http://x", "cores": [good]})
bad("config_url", {"config_url": "ftp://x/updateAll.json", "cores": [good]})
bad("config_url_type", {"config_url": ["http://x"], "cores": [good]})

good_data = data_entry("d", "http://x/d.zip", "/roms/D", {"base/d1": b"d"})
bad("data_type", {"cores": [good], "data": {"d": good_data}})
bad("data_nourl", {"cores": [good], "data": [{k: v for k, v in good_data.items() if k != "url"}]})
bad("data_url", {"cores": [good], "data": [dict(good_data, url="ftp://x/d.zip")]})
bad("data_url_name", {"cores": [good], "data": [dict(good_data, url="http://x/dir/")]})
bad("data_name", {"cores": [good], "data": [dict(good_data, files=[{"name": "a/../b", "size": 1,
                                                                    "crc": "0"}])]})
bad("data_archives", {"cores": [good], "data": [dict(good_data, archives=["a/b.zip"])]})
bad("data_dup_id", {"cores": [good], "data": [dict(good_data, id="OK")]})
bad("data_slash_in_core", {"cores": [dict(good, files=[{"name": "a/b", "size": 1, "crc": "0"}])]})
bad("data_uf2", {"cores": [good], "data": [dict(good_data, uf2={"address": "xyz", "family": "0"})]})
bad("data_uf2_type", {"cores": [good], "data": [dict(good_data, uf2="0x10200000")]})
bad("data_uf2_nofamily", {"cores": [good], "data": [dict(good_data, uf2={"address": "0x10200000"})]})
bad("data_uf2_big", {"cores": [good], "data": [dict(good_data, uf2={"address": "100000000",
                                                                    "family": "0"})]})
