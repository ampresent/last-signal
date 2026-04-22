#!/usr/bin/env python3
"""Mount Cloudflare R2 bucket as a local FUSE filesystem using s3fs + fusepy."""

import os
import sys
import errno
import stat
import tempfile
from fuse import FUSE, FuseOSError, Operations
import s3fs

R2_ACCESS_KEY = "71542fbf133953dae919680e1ba181aa"
R2_SECRET_KEY = "d99c06e3a168573f82fb801c6b0df44e9c20c42c937c54563014976385265575"
R2_ENDPOINT = "https://b532bd3cdaa12cc19553fd34b55a7c1b.r2.cloudflarestorage.com"
BUCKET = "mystore"


class R2Fuse(Operations):
    def __init__(self):
        self.fs = s3fs.S3FileSystem(
            key=R2_ACCESS_KEY,
            secret=R2_SECRET_KEY,
            endpoint_url=R2_ENDPOINT,
            client_kwargs={"region_name": "auto"},
        )
        self._cache = {}
        self._tmpdir = tempfile.mkdtemp(prefix="r2fuse_")

    def _full_path(self, path):
        # strip leading slash
        p = path.lstrip("/")
        if not p:
            return BUCKET
        return f"{BUCKET}/{p}"

    def _is_dir(self, r2path):
        try:
            return self.fs.isdir(r2path)
        except Exception:
            return False

    def getattr(self, path, fh=None):
        r2path = self._full_path(path)
        if path == "/":
            return dict(
                st_mode=stat.S_IFDIR | 0o755,
                st_nlink=2,
                st_size=0,
                st_ctime=0,
                st_mtime=0,
                st_atime=0,
            )
        try:
            info = self.fs.info(r2path)
            if info.get("type") == "directory" or info.get("StorageClass") == "DIRECTORY":
                return dict(
                    st_mode=stat.S_IFDIR | 0o755,
                    st_nlink=2,
                    st_size=0,
                    st_ctime=0,
                    st_mtime=0,
                    st_atime=0,
                )
            size = info.get("size", info.get("Size", 0))
            mtime = 0
            if "LastModified" in info:
                mtime = info["LastModified"].timestamp()
            return dict(
                st_mode=stat.S_IFREG | 0o644,
                st_nlink=1,
                st_size=size,
                st_ctime=mtime,
                st_mtime=mtime,
                st_atime=mtime,
            )
        except FileNotFoundError:
            # maybe it's a directory (prefix)
            if self._is_dir(r2path):
                return dict(
                    st_mode=stat.S_IFDIR | 0o755,
                    st_nlink=2,
                    st_size=0,
                    st_ctime=0,
                    st_mtime=0,
                    st_atime=0,
                )
            raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        r2path = self._full_path(path)
        entries = [".", ".."]
        try:
            items = self.fs.ls(r2path, detail=False)
            bucket_prefix = BUCKET + "/"
            for item in items:
                name = item
                if name.startswith(bucket_prefix):
                    name = name[len(bucket_prefix):]
                # Get just the basename
                name = name.rstrip("/").split("/")[-1]
                if name and name not in entries:
                    entries.append(name)
        except Exception:
            pass
        for e in entries:
            yield e

    def read(self, path, size, offset, fh):
        r2path = self._full_path(path)
        tmpfile = self._cache.get(path)
        if tmpfile is None or not os.path.exists(tmpfile):
            tmpfile = os.path.join(self._tmpdir, path.lstrip("/").replace("/", "_"))
            os.makedirs(os.path.dirname(tmpfile), exist_ok=True) if "/" in path.lstrip("/") else None
            try:
                self.fs.get_file(r2path, tmpfile)
            except Exception:
                raise FuseOSError(errno.EIO)
            self._cache[path] = tmpfile
        with open(tmpfile, "rb") as f:
            f.seek(offset)
            return f.read(size)

    def destroy(self, path):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <mountpoint>")
        sys.exit(1)
    mountpoint = sys.argv[1]
    if not os.path.isdir(mountpoint):
        os.makedirs(mountpoint, exist_ok=True)
    print(f"Mounting R2 bucket '{BUCKET}' at {mountpoint}")
    FUSE(R2Fuse(), mountpoint, nothreads=True, foreground=False, allow_other=False)
    print("Mounted successfully.")
