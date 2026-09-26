"""Content-addressed, no-overwrite storage with exact-byte verification."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile


def digest_file(path):
    h=hashlib.sha256()
    size=0
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024*1024):
            h.update(chunk)
            size+=len(chunk)
    return h.hexdigest(),size


def source_path(root, relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:
        raise ValueError(f'Unsafe manifest path: {relative}')
    resolved=(root/relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Source path escapes source root')
    return resolved


def archive(source, store, expected_sha, expected_size):
    destination=store/expected_sha[:2]/expected_sha
    if destination.exists():
        expected = (expected_sha, expected_size)
        if digest_file(source) != expected:
            raise ValueError(f'Source differs from audit manifest: {source.name}')
        if digest_file(destination) != expected:
            raise ValueError('Corrupt archived object; refusing to overwrite')
        return destination.resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.ingest-',dir=destination.parent)
    h=hashlib.sha256()
    size=0
    try:
        with os.fdopen(fd,'wb') as target,source.open('rb') as incoming:
            while chunk:=incoming.read(1024*1024):
                target.write(chunk)
                h.update(chunk)
                size+=len(chunk)
            target.flush()
            os.fsync(target.fileno())
        if (h.hexdigest(),size)!=(expected_sha,expected_size):
            raise ValueError(f'Source differs from audit manifest: {source.name}')
        try:
            # Atomic publish; hard-link creation fails instead of overwriting an existing object.
            os.link(temporary,destination)
        except FileExistsError:
            if digest_file(destination)!=(expected_sha,expected_size):
                raise ValueError('Corrupt archived object; refusing to overwrite')
        return destination.resolve()
    finally:
        Path(temporary).unlink(missing_ok=True)
