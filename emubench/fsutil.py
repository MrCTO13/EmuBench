"""Publish a finished file without overwriting, also on SD cards that have no hard links.

vfat and exFAT (the usual handheld and camera SD card formats) refuse link(), which the
home uses to create a file exactly once. There we fall back to a rename, which is still
atomic on one filesystem: readers see either no file or the complete one, never part of it.
"""
import errno
import os

# What link() reports on filesystems without hard links (Linux vfat/exFAT: EPERM;
# FUSE and network mounts: ENOTSUP/ENOSYS; Windows FAT: EINVAL).
NO_HARD_LINKS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL}


def publish_new(stage, dest):
    """Move a complete, fsynced stage file to dest; FileExistsError if dest already exists.

    The stage file must sit on the same filesystem as dest. After a hard link the caller
    still owns the stage file; after the rename fallback it is gone, so callers remove it
    with missing_ok."""
    try:
        os.link(stage, dest)
        return
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in NO_HARD_LINKS:
            raise
    # rename() would replace an existing file on POSIX, so check first. Two first runs
    # racing on the same card is the only window, and both files are complete.
    if os.path.lexists(dest):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(dest))
    os.rename(stage, dest)
