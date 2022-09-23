"""S3 Mirror pathing management."""
import functools
import cv2
import json
from __future__ import annotations
import os
import numpy as np
from typing import Callable, Dict, List
import boto3
from pathlib import Path
from S3MP.globals import S3MPGlobals
from S3MP.keys import (
    KeySegment,
    replace_key_segments,
    replace_key_segments_at_relative_depth,
)


def get_env_file_path() -> Path:
    """Get the mirror root from .env file."""
    root_module_folder = Path(__file__).parent.parent.resolve()
    env_file = root_module_folder / ".env"
    if not os.path.exists(f"{env_file}"):
        raise FileNotFoundError("No .env file found.")

    return env_file


def set_env_mirror_root(mirror_root: Path) -> None:
    """Set the mirror root in the .env file."""
    env_file = get_env_file_path()
    with open(f"{env_file}", "w") as f:
        f.write(f"MIRROR_ROOT={mirror_root}")


def get_env_mirror_root() -> Path:
    """Get the mirror root from .env file."""
    if S3MPGlobals.mirror_root is not None:
        return S3MPGlobals.mirror_root
    env_file = get_env_file_path()
    with open(f"{env_file}", "r") as f:
        mirror_root = f.read().strip().replace("MIRROR_ROOT=", "")

    return Path(mirror_root)


class MirrorPath:
    """A path representing an S3 file and it's local mirror."""

    def __init__(
        self, s3_key: str, local_path: Path, s3_bucket: str = S3MPGlobals.default_bucket
    ):
        """Init."""
        self._mirror_root = get_env_mirror_root()
        self.s3_key = s3_key
        self.local_path = local_path
        self.s3_bucket = s3_bucket

    @staticmethod
    def from_s3_key(s3_key: str, **kwargs: Dict) -> "MirrorPath":
        """Create a MirrorPath from an s3 key."""
        mirror_root = get_env_mirror_root()
        local_path = mirror_root / s3_key
        return MirrorPath(s3_key, local_path, **kwargs)

    @staticmethod
    def from_local_path(local_path: Path, **kwargs: Dict) -> "MirrorPath":
        """Create a MirrorPath from a local path."""
        mirror_root = get_env_mirror_root()
        s3_key = local_path.relative_to(mirror_root).as_posix()
        return MirrorPath(s3_key, local_path, **kwargs)

    def exists_in_mirror(self) -> bool:
        """Check if file exists in mirror."""
        return self.local_path.exists()

    def exists_on_s3(self) -> bool:
        """Check if file exists on S3."""
        s3_client = S3MPGlobals.s3_client
        results = s3_client.list_objects_v2(Bucket=self.s3_bucket, Prefix=self.s3_key)
        return "Contents" in results

    def download_to_mirror_if_not_present(self):
        """Download to mirror if not present."""
        if not self.exists_in_mirror():
            self.download_to_mirror()

    def download_to_mirror(self, overwrite: bool = False):
        """Download S3 file to mirror."""
        local_folder = self.local_path.parent
        local_folder.mkdir(parents=True, exist_ok=True)

        s3_resource = S3MPGlobals.s3_resource
        bucket = s3_resource.Bucket(self.s3_bucket)
        if not overwrite and self.exists_in_mirror():
            return
        # TODO handle folder.
        bucket.download_file(
            self.s3_key,
            self.local_path,
            Callback=S3MPGlobals.callback,
            Config=S3MPGlobals.transfer_config,
        )

    def upload_from_mirror(self):
        """Upload local file to S3."""
        s3_resource = boto3.resource("s3")
        bucket = s3_resource.Bucket(self.s3_bucket)
        # TODO put configs in a more central spot
        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=1024 * 25,
            max_concurrency=20,
            multipart_chunksize=1024 * 25,
            use_threads=True,
        )
        bucket.upload_file(
            self.local_path,
            self.s3_key,
            Callback=S3MPGlobals.callback,
            Config=transfer_config,
        )

    def replace_key_segments(self, segments: List[KeySegment]) -> MirrorPath:
        """Replace key segments."""
        new_key = replace_key_segments(self.s3_key, segments)
        return MirrorPath.from_s3_key(new_key)

    def replace_key_segments_at_relative_depth(
        self, segments: List[KeySegment]
    ) -> MirrorPath:
        """Replace key segments at relative depth."""
        new_key = replace_key_segments_at_relative_depth(self.s3_key, segments)
        return MirrorPath.from_s3_key(new_key)

    def get_sibling(self, sibling_name: str) -> MirrorPath:
        """Get a file with the same parent as this file."""
        return self.replace_key_segments_at_relative_depth(
            [KeySegment(0, sibling_name)]
        )
    
    def get_child(self, child_name: str) -> MirrorPath:
        """Get a file with the same parent as this file."""
        return self.replace_key_segments_at_relative_depth(
            [KeySegment(1, child_name)]
        )
    
    def get_parent(self) -> MirrorPath:
        """Get the parent of this file."""
        stripped_key = "/".join([seg for seg in self.s3_key.split("/") if seg][:-1])
        return MirrorPath.from_s3_key(stripped_key)

    def load_local(self, download: bool = True, load_fn: Callable = None):
        """
        Load local file, infer file type and load.
        Setting download to false will still download if the file is not present.
        """
        if download or not self.exists_in_mirror():
            self.download_to_mirror()
        if load_fn is None:
            match (self.local_path.suffix):
                case ".json":
                    load_fn = functools.partial(json.load, open(self.local_path))
                case ".npy":
                    load_fn = np.load
                case ".jpg" | ".jpeg" | ".png":
                    load_fn = cv2.imread

        data = load_fn(str(self.local_path))
        return data

    def save_local(self, data, upload: bool = True, save_fn: Callable = None):
        """Save local file, infer file type and upload."""
        if save_fn is None:
            match (self.local_path.suffix):
                case ".json":
                    save_fn = functools.partial(json.dump, fp=open(str(self.local_path), "w"))
                case ".npy":
                    save_fn = functools.partial(np.save, file=str(self.local_path))
                case ".jpg" | ".jpeg" | ".png":
                    save_fn = functools.partial(cv2.imwrite, filename=str(self.local_path))
        save_fn(data)
        if upload:
            self.upload_from_mirror()

    def __repr__(self):
        """Repr."""
        return f"{self.__class__.__name__}({self.s3_key}, {self.local_path}, {self.s3_bucket})"
