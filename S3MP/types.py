"""Types, mostly from mypy_boto3 (boto3-stubs)."""
from pathlib import Path
from mypy_boto3_s3 import S3Client, S3ServiceResource as S3Resource
from mypy_boto3_s3.service_resource import Bucket as S3Bucket
from s3transfer.manager import TransferConfig as S3TransferConfig
from typing import NewType, TypeVar, Union, List, Any, Generic, ParamSpec, Mapping

T = TypeVar('T')
SList = List[T] | T 
PathSList = SList[Path]
StrSSlist = SList[str]